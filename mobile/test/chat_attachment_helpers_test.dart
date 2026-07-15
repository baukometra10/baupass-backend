import 'package:baupass_worker/features/chat/chat_attachment_helpers.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('chat attachment classification', () {
    test('jpeg is image not audio', () {
      final att = {
        'filename': 'foto.jpg',
        'contentType': 'image/jpeg',
      };
      expect(isChatImageAttachment(att), isTrue);
      expect(isChatAudioAttachment(att), isFalse);
    });

    test('e2e image meta is image not audio', () {
      final att = {
        'filename': 'upload.bin.e2e',
        'contentType': 'application/vnd.suppix.e2e+binary',
        'e2eMeta': '{"mime":"image/png","filename":"shot.png"}',
      };
      expect(isChatImageAttachment(att), isTrue);
      expect(isChatAudioAttachment(att), isFalse);
    });

    test('voice webm is audio', () {
      final att = {
        'filename': 'voice-1.webm',
        'contentType': 'audio/webm',
      };
      expect(isChatAudioAttachment(att), isTrue);
      expect(isChatImageAttachment(att), isFalse);
    });

    test('octet-stream jpg by extension is image', () {
      final att = {
        'filename': 'camera.jpg',
        'contentType': 'application/octet-stream',
      };
      expect(isChatImageAttachment(att), isTrue);
      expect(isChatAudioAttachment(att), isFalse);
    });
  });
}
