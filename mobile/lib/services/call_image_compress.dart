import 'dart:typed_data';

import 'package:image/image.dart' as img;

/// Compress an in-call photo for the signaling channel (~160KB data URL budget).
Uint8List compressCallImageBytes(
  Uint8List input, {
  int maxEdge = 720,
  int initialQuality = 68,
  int maxEncodedBytes = 140000,
}) {
  final decoded = img.decodeImage(input);
  if (decoded == null) {
    throw ArgumentError('invalid_image');
  }

  var working = decoded;
  final longest = working.width > working.height ? working.width : working.height;
  if (longest > maxEdge) {
    if (working.width >= working.height) {
      working = img.copyResize(working, width: maxEdge);
    } else {
      working = img.copyResize(working, height: maxEdge);
    }
  }

  var quality = initialQuality;
  var encoded = Uint8List.fromList(img.encodeJpg(working, quality: quality));
  var guard = 0;
  while (encoded.length > maxEncodedBytes && guard < 8) {
    guard += 1;
    if (quality > 40) {
      quality -= 10;
    } else {
      final nextW = (working.width * 0.78).round().clamp(280, working.width);
      final nextH = (working.height * 0.78).round().clamp(280, working.height);
      if (nextW >= working.width && nextH >= working.height) break;
      working = img.copyResize(working, width: nextW, height: nextH);
      quality = quality.clamp(35, 55);
    }
    encoded = Uint8List.fromList(img.encodeJpg(working, quality: quality));
  }
  if (encoded.length > 220000) {
    throw ArgumentError('call_image_too_large');
  }
  return encoded;
}
