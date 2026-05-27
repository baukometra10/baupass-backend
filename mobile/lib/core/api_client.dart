import 'dart:convert';

import 'package:http/http.dart' as http;

import 'config.dart';

class ApiException implements Exception {
  ApiException(this.statusCode, this.errorCode, [this.message]);

  final int statusCode;
  final String? errorCode;
  final String? message;

  @override
  String toString() => 'ApiException($statusCode, $errorCode, $message)';
}

class ApiClient {
  ApiClient({http.Client? httpClient, String? baseUrl})
      : _http = httpClient ?? http.Client(),
        _baseUrl = (baseUrl ?? AppConfig.apiBaseUrl).replaceAll(RegExp(r'/+$'), '');

  final http.Client _http;
  final String _baseUrl;

  Future<Map<String, dynamic>> postJson(
    String path, {
    Map<String, dynamic>? body,
    String? bearerToken,
  }) async {
    final uri = Uri.parse('$_baseUrl$path');
    final headers = <String, String>{
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    };
    if (bearerToken != null && bearerToken.isNotEmpty) {
      headers['Authorization'] = 'Bearer $bearerToken';
    }
    final http.Response response;
    try {
      response = await _http.post(
        uri,
        headers: headers,
        body: jsonEncode(body ?? <String, dynamic>{}),
      );
    } on Exception catch (e) {
      throw ApiException(0, 'network_error', e.toString());
    }
    Map<String, dynamic> decoded = <String, dynamic>{};
    if (response.body.isNotEmpty) {
      final parsed = jsonDecode(response.body);
      if (parsed is Map<String, dynamic>) {
        decoded = parsed;
      }
    }
    if (response.statusCode >= 400) {
      throw ApiException(
        response.statusCode,
        decoded['error'] as String?,
        decoded['message'] as String?,
      );
    }
    return decoded;
  }

  Future<List<Map<String, dynamic>>> getJsonList(String path, {String? bearerToken}) async {
    final uri = Uri.parse('$_baseUrl$path');
    final headers = <String, String>{'Accept': 'application/json'};
    if (bearerToken != null && bearerToken.isNotEmpty) {
      headers['Authorization'] = 'Bearer $bearerToken';
    }
    final http.Response response;
    try {
      response = await _http.get(uri, headers: headers);
    } on Exception catch (e) {
      throw ApiException(0, 'network_error', e.toString());
    }
    if (response.statusCode >= 400) {
      Map<String, dynamic> decoded = <String, dynamic>{};
      if (response.body.isNotEmpty) {
        final parsed = jsonDecode(response.body);
        if (parsed is Map<String, dynamic>) decoded = parsed;
      }
      throw ApiException(
        response.statusCode,
        decoded['error'] as String?,
        decoded['message'] as String?,
      );
    }
    if (response.body.isEmpty) return <Map<String, dynamic>>[];
    final parsed = jsonDecode(response.body);
    if (parsed is! List) return <Map<String, dynamic>>[];
    return parsed
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .toList();
  }

  Future<Map<String, dynamic>> getJson(String path, {String? bearerToken}) async {
    final uri = Uri.parse('$_baseUrl$path');
    final headers = <String, String>{'Accept': 'application/json'};
    if (bearerToken != null && bearerToken.isNotEmpty) {
      headers['Authorization'] = 'Bearer $bearerToken';
    }
    final http.Response response;
    try {
      response = await _http.get(uri, headers: headers);
    } on Exception catch (e) {
      throw ApiException(0, 'network_error', e.toString());
    }
    Map<String, dynamic> decoded = <String, dynamic>{};
    if (response.body.isNotEmpty) {
      final parsed = jsonDecode(response.body);
      if (parsed is Map<String, dynamic>) {
        decoded = parsed;
      }
    }
    if (response.statusCode >= 400) {
      throw ApiException(
        response.statusCode,
        decoded['error'] as String?,
        decoded['message'] as String?,
      );
    }
    return decoded;
  }

  void close() => _http.close();
}
