import 'dart:convert';
import 'dart:typed_data';

import 'package:cryptography/cryptography.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Client-side E2E crypto for Flutter (X25519 + AES-GCM). Private keys never leave secure storage.
class E2eCryptoService {
  E2eCryptoService({FlutterSecureStorage? storage})
      : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;
  final X25519 _x25519 = X25519();
  final AesGcm _aesGcm = AesGcm.with256bits();

  String _identityKey(String entityType, String entityId) =>
      'suppix-e2e:$entityType:$entityId';

  static const _macLength = 16;

  Uint8List _gcmWireBytes(SecretBox box) {
    return Uint8List.fromList([...box.cipherText, ...box.mac.bytes]);
  }

  SecretBox _secretBoxFromWire(Uint8List wire, List<int> nonce) {
    if (wire.length <= _macLength) {
      throw StateError('e2e_attachment_ciphertext_invalid');
    }
    return SecretBox(
      wire.sublist(0, wire.length - _macLength),
      nonce: nonce,
      mac: Mac(wire.sublist(wire.length - _macLength)),
    );
  }

  Future<List<int>> _decryptGcmBytes(Uint8List cipherBytes, SecretKey aesKey, List<int> nonce) async {
    try {
      return await _aesGcm.decrypt(
        _secretBoxFromWire(cipherBytes, nonce),
        secretKey: aesKey,
      );
    } catch (_) {
      return await _aesGcm.decrypt(
        SecretBox(cipherBytes, nonce: nonce, mac: Mac.empty),
        secretKey: aesKey,
      );
    }
  }

  Future<Map<String, dynamic>> ensureIdentity({
    required String entityType,
    required String entityId,
  }) async {
    final key = _identityKey(entityType, entityId);
    final existing = await _storage.read(key: key);
    if (existing != null && existing.isNotEmpty) {
      final parsed = jsonDecode(existing) as Map<String, dynamic>;
      return {
        'entityType': entityType,
        'entityId': entityId,
        'publicKeySpkiB64': parsed['publicKeySpkiB64'] as String,
        'algorithm': 'X25519',
      };
    }
    final keyPair = await _x25519.newKeyPair();
    final publicKey = await keyPair.extractPublicKey();
    final publicKeySpkiB64 = base64Encode(publicKey.bytes);
    final privateKeyBytes = await keyPair.extractPrivateKeyBytes();
    await _storage.write(
      key: key,
      value: jsonEncode({
        'publicKeySpkiB64': publicKeySpkiB64,
        'privateKeyBytes': base64Encode(privateKeyBytes),
        'algorithm': 'X25519',
      }),
    );
    return {
      'entityType': entityType,
      'entityId': entityId,
      'publicKeySpkiB64': publicKeySpkiB64,
      'algorithm': 'X25519',
    };
  }

  Future<Map<String, dynamic>> ensureLocalIdentity({
    required String entityType,
    required String entityId,
  }) =>
      ensureIdentity(entityType: entityType, entityId: entityId);

  bool isE2eEnvelope(String value) {
    try {
      final parsed = jsonDecode(value);
      if (parsed is! Map) return false;
      return parsed['e2e'] == true && parsed['v'] != null && parsed['ct'] != null;
    } catch (_) {
      return false;
    }
  }

  Future<String> encryptUtf8(String plaintext, List<String> recipientPublicKeysSpkiB64) async {
    final recipients = recipientPublicKeysSpkiB64.where((k) => k.trim().isNotEmpty).toList();
    if (recipients.isEmpty) throw StateError('e2e_recipients_required');
    final envelopes = <Map<String, dynamic>>[];
    for (final pubB64 in recipients) {
      envelopes.add(await _sealForRecipient(plaintext, pubB64));
    }
    if (envelopes.length == 1) return jsonEncode(envelopes.first);
    return jsonEncode({'e2e': true, 'v': 1, 'multi': true, 'envelopes': envelopes});
  }

  Future<String> decryptUtf8(String storedBody, String entityType, String entityId) async {
    if (!isE2eEnvelope(storedBody)) return storedBody;
    final parsed = jsonDecode(storedBody);
    final privateKey = await _loadPrivateKey(entityType, entityId);
    if (parsed is Map && parsed['multi'] == true && parsed['envelopes'] is List) {
      for (final item in parsed['envelopes'] as List) {
        try {
          return await _openEnvelope(Map<String, dynamic>.from(item as Map), privateKey);
        } catch (_) {}
      }
      throw StateError('e2e_decrypt_failed');
    }
    return _openEnvelope(Map<String, dynamic>.from(parsed as Map), privateKey);
  }

  Future<Map<String, dynamic>> encryptBlob(
    Uint8List fileBytes,
    List<String> recipientPublicKeysSpkiB64, {
    required String filename,
    required String mime,
    int? durationSec,
    bool viewOnce = false,
  }) async {
    final secretKey = await _aesGcm.newSecretKey();
    final nonce = _aesGcm.newNonce();
    final secretBox = await _aesGcm.encrypt(fileBytes, secretKey: secretKey, nonce: nonce);
    final wireBytes = _gcmWireBytes(secretBox);
    final keyBytes = await secretKey.extractBytes();
    final keyB64 = base64Encode(keyBytes);
    final wrappedKey = await encryptUtf8(keyB64, recipientPublicKeysSpkiB64);
    final meta = {
      'e2e': true,
      'v': 1,
      'kind': 'attachment',
      'alg': 'X25519-AES-GCM',
      'filename': filename,
      'mime': mime,
      if (durationSec != null && durationSec > 0) 'durationSec': durationSec,
      if (viewOnce) 'viewOnce': true,
      'iv': base64Encode(nonce),
      'ct': base64Encode(wireBytes),
      'wrappedKey': wrappedKey,
    };
    return {'blob': wireBytes, 'meta': jsonEncode(meta)};
  }

  Future<({Uint8List bytes, String filename, String mime})> decryptBlob(
    Uint8List cipherBytes,
    String metaJson,
    String entityType,
    String entityId,
  ) async {
    final meta = jsonDecode(metaJson) as Map<String, dynamic>;
    final keyB64 = await decryptUtf8(meta['wrappedKey'] as String, entityType, entityId);
    final secretKey = SecretKey(base64Decode(keyB64));
    final nonce = base64Decode(meta['iv'] as String);
    final clear = await _decryptGcmBytes(cipherBytes, secretKey, nonce);
    return (
      bytes: Uint8List.fromList(clear),
      filename: meta['filename'] as String? ?? 'download.bin',
      mime: meta['mime'] as String? ?? 'application/octet-stream',
    );
  }

  Future<SimpleKeyPair> _loadPrivateKey(String entityType, String entityId) async {
    final raw = await _storage.read(key: _identityKey(entityType, entityId));
    if (raw == null || raw.isEmpty) throw StateError('e2e_private_key_missing');
    final parsed = jsonDecode(raw) as Map<String, dynamic>;
    return SimpleKeyPairData(
      base64Decode(parsed['privateKeyBytes'] as String),
      type: KeyPairType.x25519,
      publicKey: SimplePublicKey(
        base64Decode(parsed['publicKeySpkiB64'] as String),
        type: KeyPairType.x25519,
      ),
    );
  }

  Future<Map<String, dynamic>> _sealForRecipient(String plaintext, String recipientPublicKeySpkiB64) async {
    final ephemeral = await _x25519.newKeyPair();
    final recipientPublic = SimplePublicKey(
      base64Decode(recipientPublicKeySpkiB64),
      type: KeyPairType.x25519,
    );
    final shared = await _x25519.sharedSecretKey(
      keyPair: ephemeral,
      remotePublicKey: recipientPublic,
    );
    final aesKey = SecretKey(await shared.extractBytes().then((b) => b.sublist(0, 32)));
    final nonce = _aesGcm.newNonce();
    final secretBox = await _aesGcm.encrypt(
      utf8.encode(plaintext),
      secretKey: aesKey,
      nonce: nonce,
    );
    final ephemeralPublic = await ephemeral.extractPublicKey();
    return {
      'e2e': true,
      'v': 1,
      'alg': 'X25519-AES-GCM',
      'epk': base64Encode(ephemeralPublic.bytes),
      'iv': base64Encode(nonce),
      'ct': base64Encode(_gcmWireBytes(secretBox)),
    };
  }

  Future<String> _openEnvelope(Map<String, dynamic> envelope, SimpleKeyPair privateKey) async {
    final ephemeralPublic = SimplePublicKey(
      base64Decode(envelope['epk'] as String),
      type: KeyPairType.x25519,
    );
    final shared = await _x25519.sharedSecretKey(
      keyPair: privateKey,
      remotePublicKey: ephemeralPublic,
    );
    final aesKey = SecretKey(await shared.extractBytes().then((b) => b.sublist(0, 32)));
    final nonce = base64Decode(envelope['iv'] as String);
    final cipherText = base64Decode(envelope['ct'] as String);
    final clear = await _decryptGcmBytes(Uint8List.fromList(cipherText), aesKey, nonce);
    return utf8.decode(clear);
  }
}
