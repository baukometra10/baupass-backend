import 'dart:convert';

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

  Map<String, String> _headers({
    String? bearerToken,
    String? deviceId,
    bool jsonBody = false,
  }) {
    final headers = <String, String>{'Accept': 'application/json'};
    if (jsonBody) headers['Content-Type'] = 'application/json';
    if (bearerToken != null && bearerToken.isNotEmpty) {
      headers['Authorization'] = 'Bearer $bearerToken';
    }
    if (deviceId != null && deviceId.isNotEmpty) {
      headers['X-Device-Id'] = deviceId;
    }
    return headers;
  }

  void _maybeNotifySessionExpired(int statusCode, String? errorCode) {
    if (statusCode == 401 &&
        (errorCode == 'invalid_worker_session' ||
            errorCode == 'worker_session_expired' ||
            errorCode == 'worker_not_available')) {
      onSessionExpired?.call();
    }
  }

  Future<Map<String, dynamic>> postJson(
    String path, {
    Map<String, dynamic>? body,
    String? bearerToken,
    String? deviceId,
  }) async {
    final uri = Uri.parse('$_baseUrl$path');
    final http.Response response;
    try {
      response = await _http.post(
        uri,
        headers: _headers(bearerToken: bearerToken, deviceId: deviceId, jsonBody: true),
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
  }) async {
    final uri = Uri.parse('$_baseUrl$path');
    final http.Response response;
    try {
      response = await _http.get(
        uri,
        headers: _headers(bearerToken: bearerToken, deviceId: deviceId),
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
  }) async {
    final uri = Uri.parse('$_baseUrl$path');
    final http.Response response;
    try {
      response = await _http.get(
        uri,
        headers: _headers(bearerToken: bearerToken, deviceId: deviceId),
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

  void close() => _http.close();
}
