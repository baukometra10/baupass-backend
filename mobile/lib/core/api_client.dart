import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import 'config.dart';

class ApiException implements Exception {
  ApiException(this.statusCode, this.errorCode, [this.message]);

  final int statusCode;
  final String? errorCode;
  final String? message;

  @override
  String toString() => message ?? 'ApiException($statusCode, $errorCode)';
}

typedef SessionExpiredCallback = void Function();

class ApiClient {
  ApiClient({http.Client? httpClient, String? baseUrl, this.onSessionExpired})
      : _http = httpClient ?? http.Client(),
        _baseUrl = (baseUrl ?? AppConfig.apiBaseUrl).replaceAll(RegExp(r'/+$'), '');

  final http.Client _http;
  final String _baseUrl;
  SessionExpiredCallback? onSessionExpired;

  String get baseUrl => _baseUrl;

  Map<String, String> _headers({
    String? bearerToken,
    String? deviceId,
    bool jsonBody = false,
    Map<String, String>? extraHeaders,
  }) {
    final headers = <String, String>{'Accept': 'application/json'};
    if (jsonBody) headers['Content-Type'] = 'application/json';
    if (bearerToken != null && bearerToken.isNotEmpty) {
      headers['Authorization'] = 'Bearer $bearerToken';
    }
    if (deviceId != null && deviceId.isNotEmpty) {
      headers['X-Device-Id'] = deviceId;
    }
    if (extraHeaders != null && extraHeaders.isNotEmpty) {
      headers.addAll(extraHeaders);
    }
    return headers;
  }

  void _maybeNotifySessionExpired(int statusCode, String? errorCode) {
    final reloginCodes = {
      'invalid_worker_session',
      'worker_session_expired',
      'worker_not_available',
      'missing_device_id',
      'device_not_bound',
      'device_not_active',
    };
    if ((statusCode == 401 || statusCode == 403) &&
        errorCode != null &&
        reloginCodes.contains(errorCode)) {
      onSessionExpired?.call();
    }
  }

  Future<Map<String, dynamic>> postJson(
    String path, {
    Map<String, dynamic>? body,
    String? bearerToken,
    String? deviceId,
    Map<String, String>? extraHeaders,
  }) async {
    final uri = Uri.parse('$_baseUrl$path');
    final http.Response response;
    try {
      response = await _http.post(
        uri,
        headers: _headers(
          bearerToken: bearerToken,
          deviceId: deviceId,
          jsonBody: true,
          extraHeaders: extraHeaders,
        ),
        body: jsonEncode(body ?? <String, dynamic>{}),
      );
    } on Exception catch (e) {
      throw ApiException(0, 'network_error', e.toString());
    }
    Map<String, dynamic> decoded = <String, dynamic>{};
    if (response.body.isNotEmpty) {
      final parsed = jsonDecode(response.body);
      if (parsed is Map<String, dynamic>) decoded = parsed;
    }
    if (response.statusCode >= 400) {
      final errorCode = decoded['error'] as String?;
      _maybeNotifySessionExpired(response.statusCode, errorCode);
      throw ApiException(
        response.statusCode,
        errorCode,
        decoded['message'] as String?,
      );
    }
    return decoded;
  }

  Future<Map<String, dynamic>> putJson(
    String path, {
    Map<String, dynamic>? body,
    String? bearerToken,
    String? deviceId,
    Map<String, String>? extraHeaders,
  }) async {
    final uri = Uri.parse('$_baseUrl$path');
    final http.Response response;
    try {
      response = await _http.put(
        uri,
        headers: _headers(
          bearerToken: bearerToken,
          deviceId: deviceId,
          jsonBody: true,
          extraHeaders: extraHeaders,
        ),
        body: jsonEncode(body ?? <String, dynamic>{}),
      );
    } on Exception catch (e) {
      throw ApiException(0, 'network_error', e.toString());
    }
    Map<String, dynamic> decoded = <String, dynamic>{};
    if (response.body.isNotEmpty) {
      final parsed = jsonDecode(response.body);
      if (parsed is Map<String, dynamic>) decoded = parsed;
    }
    if (response.statusCode >= 400) {
      final errorCode = decoded['error'] as String?;
      _maybeNotifySessionExpired(response.statusCode, errorCode);
      throw ApiException(
        response.statusCode,
        errorCode,
        decoded['message'] as String?,
      );
    }
    return decoded;
  }

  Future<List<Map<String, dynamic>>> getJsonList(
    String path, {
    String? bearerToken,
    String? deviceId,
    Map<String, String>? extraHeaders,
  }) async {
    final uri = Uri.parse('$_baseUrl$path');
    final http.Response response;
    try {
      response = await _http.get(
        uri,
        headers: _headers(
          bearerToken: bearerToken,
          deviceId: deviceId,
          extraHeaders: extraHeaders,
        ),
      );
    } on Exception catch (e) {
      throw ApiException(0, 'network_error', e.toString());
    }
    if (response.statusCode >= 400) {
      Map<String, dynamic> decoded = <String, dynamic>{};
      if (response.body.isNotEmpty) {
        final parsed = jsonDecode(response.body);
        if (parsed is Map<String, dynamic>) decoded = parsed;
      }
      final errorCode = decoded['error'] as String?;
      _maybeNotifySessionExpired(response.statusCode, errorCode);
      throw ApiException(
        response.statusCode,
        errorCode,
        decoded['message'] as String?,
      );
    }
    if (response.body.isEmpty) return <Map<String, dynamic>>[];
    final parsed = jsonDecode(response.body);
    if (parsed is! List) return <Map<String, dynamic>>[];
    return parsed.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();
  }

  Future<Map<String, dynamic>> getJson(
    String path, {
    String? bearerToken,
    String? deviceId,
    Map<String, String>? extraHeaders,
  }) async {
    final uri = Uri.parse('$_baseUrl$path');
    final http.Response response;
    try {
      response = await _http.get(
        uri,
        headers: _headers(
          bearerToken: bearerToken,
          deviceId: deviceId,
          extraHeaders: extraHeaders,
        ),
      );
    } on Exception catch (e) {
      throw ApiException(0, 'network_error', e.toString());
    }
    Map<String, dynamic> decoded = <String, dynamic>{};
    if (response.body.isNotEmpty) {
      final parsed = jsonDecode(response.body);
      if (parsed is Map<String, dynamic>) decoded = parsed;
    }
    if (response.statusCode >= 400) {
      final errorCode = decoded['error'] as String?;
      _maybeNotifySessionExpired(response.statusCode, errorCode);
      throw ApiException(
        response.statusCode,
        errorCode,
        decoded['message'] as String?,
      );
    }
    return decoded;
  }

  Future<Uint8List> getBytes(
    String path, {
    String? bearerToken,
    String? deviceId,
    Map<String, String>? extraHeaders,
  }) async {
    final uri = Uri.parse(path.startsWith('http') ? path : '$_baseUrl$path');
    final http.Response response;
    try {
      response = await _http.get(
        uri,
        headers: _headers(
          bearerToken: bearerToken,
          deviceId: deviceId,
          extraHeaders: extraHeaders,
        ),
      );
    } on Exception catch (e) {
      throw ApiException(0, 'network_error', e.toString());
    }
    if (response.statusCode >= 400) {
      throw ApiException(response.statusCode, 'http_${response.statusCode}');
    }
    return Uint8List.fromList(response.bodyBytes);
  }

  Future<Map<String, dynamic>> postMultipart(
    String path, {
    required Map<String, String> fields,
    required File file,
    required String fileField,
    String? bearerToken,
    String? deviceId,
    Map<String, String>? extraHeaders,
  }) async {
    final uri = Uri.parse('$_baseUrl$path');
    final request = http.MultipartRequest('POST', uri);
    request.headers.addAll(_headers(
      bearerToken: bearerToken,
      deviceId: deviceId,
      extraHeaders: extraHeaders,
    ));
    request.fields.addAll(fields);
    request.files.add(await http.MultipartFile.fromPath(fileField, file.path));
    http.StreamedResponse streamed;
    try {
      streamed = await request.send();
    } on Exception catch (e) {
      throw ApiException(0, 'network_error', e.toString());
    }
    final response = await http.Response.fromStream(streamed);
    Map<String, dynamic> decoded = <String, dynamic>{};
    if (response.body.isNotEmpty) {
      final parsed = jsonDecode(response.body);
      if (parsed is Map<String, dynamic>) decoded = parsed;
    }
    if (response.statusCode >= 400) {
      final errorCode = decoded['error'] as String?;
      _maybeNotifySessionExpired(response.statusCode, errorCode);
      throw ApiException(
        response.statusCode,
        errorCode,
        decoded['message'] as String?,
      );
    }
    return decoded;
  }

  void close() => _http.close();
}
