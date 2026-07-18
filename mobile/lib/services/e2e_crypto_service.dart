import 'dart:convert';
import 'dart:typed_data';

import 'package:cryptography/cryptography.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Client-side E2E crypto for Flutter (X25519 + AES-GCM). Private keys never leave secure storage.
///
/// Public keys are stored/published as real SPKI (RFC 8410) so Web Crypto admin clients can import them.
class E2eCryptoService {
  E2eCryptoService({FlutterSecureStorage? storage})
      : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;
  final X25519 _x25519 = X25519();
  final AesGcm _aesGcm = AesGcm.with256bits();

  /// ASN.1 SPKI prefix for X25519 SubjectPublicKeyInfo (RFC 8410).
  static final Uint8List _x25519SpkiPrefix = Uint8List.fromList(<int>[
    0x30, 0x2a, // SEQUENCE, 42 bytes
    0x30, 0x05, // AlgorithmIdentifier SEQUENCE
    0x06, 0x03, 0x2b, 0x65, 0x6e, // OID 1.3.101.110 (X25519)
    0x03, 0x21, 0x00, // BIT STRING, 33 bytes, 0 unused bits
  ]);

  String _identityKey(String entityType, String entityId) =>
      'suppix-e2e:$entityType:$entityId';

  static const _macLength = 16;

  /// Convert raw 32-byte X25519 public key to SPKI base64 (Web-compatible).
  static String rawPublicKeyToSpkiB64(List<int> raw) {
    if (raw.length != 32) {
      throw StateError('e2e_public_key_raw_invalid');
    }
    return base64Encode(Uint8List.fromList([..._x25519SpkiPrefix, ...raw]));
  }

  /// Accept SPKI or legacy raw-32 base64; return raw 32 bytes for cryptography package.
  static Uint8List publicKeySpkiOrRawToBytes(String spkiOrRawB64) {
    final bytes = base64Decode(spkiOrRawB64.trim());
    if (bytes.length == 32) return Uint8List.fromList(bytes);
    if (bytes.length == 44 &&
        bytes.length >= _x25519SpkiPrefix.length + 32 &&
        _startsWith(bytes, _x25519SpkiPrefix)) {
      return Uint8List.fromList(bytes.sublist(bytes.length - 32));
    }
    // Some exporters omit unused-bits byte variations — take last 32 if long enough.
    if (bytes.length > 32) {
      return Uint8List.fromList(bytes.sublist(bytes.length - 32));
    }
    throw StateError('e2e_public_key_spki_invalid');
  }

  static bool _startsWith(List<int> bytes, List<int> prefix) {
    if (bytes.length < prefix.length) return false;
    for (var i = 0; i < prefix.length; i++) {
      if (bytes[i] != prefix[i]) return false;
    }
    return true;
  }

  static bool _looksLikeSpki(String b64) {
    try {
      final bytes = base64Decode(b64.trim());
      return bytes.length == 44 && _startsWith(bytes, _x25519SpkiPrefix);
    } catch (_) {
      return false;
    }
  }

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
      final parsed = Map<String, dynamic>.from(jsonDecode(existing) as Map);
      final migrated = await _migrateIdentityIfNeeded(key, parsed);
      return {
        'entityType': entityType,
        'entityId': entityId,
        'publicKeySpkiB64': migrated['publicKeySpkiB64'] as String,
        'algorithm': 'X25519',
        if (migrated['needsRepublish'] == true) 'needsRepublish': true,
      };
    }
    final keyPair = await _x25519.newKeyPair();
    final publicKey = await keyPair.extractPublicKey();
    final publicKeySpkiB64 = rawPublicKeyToSpkiB64(publicKey.bytes);
    final privateKeyBytes = await keyPair.extractPrivateKeyBytes();
    await _storage.write(
      key: key,
      value: jsonEncode({
        'publicKeySpkiB64': publicKeySpkiB64,
        'privateKeyBytes': base64Encode(privateKeyBytes),
        'algorithm': 'X25519',
        'format': 'spki-v1',
      }),
    );
    return {
      'entityType': entityType,
      'entityId': entityId,
      'publicKeySpkiB64': publicKeySpkiB64,
      'algorithm': 'X25519',
      'needsRepublish': true,
    };
  }

  /// Upgrade legacy raw-32 public keys stored as publicKeySpkiB64 to real SPKI.
  Future<Map<String, dynamic>> _migrateIdentityIfNeeded(
    String storageKey,
    Map<String, dynamic> parsed,
  ) async {
    final pubB64 = (parsed['publicKeySpkiB64'] as String? ?? '').trim();
    if (pubB64.isEmpty) throw StateError('e2e_public_key_missing');
    if (_looksLikeSpki(pubB64) && parsed['format'] == 'spki-v1') {
      return parsed;
    }
    final raw = publicKeySpkiOrRawToBytes(pubB64);
    final spkiB64 = rawPublicKeyToSpkiB64(raw);
    final next = <String, dynamic>{
      ...parsed,
      'publicKeySpkiB64': spkiB64,
      'format': 'spki-v1',
      'needsRepublish': true,
    };
    await _storage.write(key: storageKey, value: jsonEncode({
      'publicKeySpkiB64': spkiB64,
      'privateKeyBytes': parsed['privateKeyBytes'],
      'algorithm': 'X25519',
      'format': 'spki-v1',
    }));
    return next;
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
      if (parsed['e2e'] == true && parsed['multi'] == true && parsed['envelopes'] is List) {
        return true;
      }
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
    final parsed = Map<String, dynamic>.from(jsonDecode(raw) as Map);
    final migrated = await _migrateIdentityIfNeeded(_identityKey(entityType, entityId), parsed);
    final pubRaw = publicKeySpkiOrRawToBytes(migrated['publicKeySpkiB64'] as String);
    return SimpleKeyPairData(
      base64Decode(migrated['privateKeyBytes'] as String),
      type: KeyPairType.x25519,
      publicKey: SimplePublicKey(pubRaw, type: KeyPairType.x25519),
    );
  }

  Future<Map<String, dynamic>> _sealForRecipient(String plaintext, String recipientPublicKeySpkiB64) async {
    final ephemeral = await _x25519.newKeyPair();
    final recipientPublic = SimplePublicKey(
      publicKeySpkiOrRawToBytes(recipientPublicKeySpkiB64),
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
      publicKeySpkiOrRawToBytes(envelope['epk'] as String),
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
