import 'dart:convert';

/// Shared attachment classification (image vs audio) for chat bubbles + tests.
Map<String, dynamic>? parseE2eAttachmentMeta(dynamic raw) {
  if (raw is Map) return Map<String, dynamic>.from(raw);
  final text = raw?.toString().trim() ?? '';
  if (text.isEmpty) return null;
  try {
    final decoded = jsonDecode(text);
    if (decoded is Map) return Map<String, dynamic>.from(decoded);
  } catch (_) {
    /* ignore invalid meta */
  }
  return null;
}

bool isChatImageAttachment(Map<String, dynamic> attachment) {
  final meta = parseE2eAttachmentMeta(attachment['e2eMeta'] ?? attachment['e2e_meta']);
  final metaMime = (meta?['mime'] ?? '').toString().toLowerCase();
  final metaName = (meta?['filename'] ?? '').toString().toLowerCase();
  final contentType = (attachment['contentType'] ?? attachment['content_type'] ?? metaMime)
      .toString()
      .toLowerCase();
  final filename = (metaName.isNotEmpty ? metaName : (attachment['filename'] ?? ''))
      .toString()
      .toLowerCase();
  if (contentType.startsWith('image/')) return true;
  return RegExp(r'\.(jpe?g|png|webp|gif|heic|heif)(\.e2e)?$', caseSensitive: false)
      .hasMatch(filename);
}

bool isChatAudioAttachment(Map<String, dynamic> attachment) {
  if (isChatImageAttachment(attachment)) return false;
  final meta = parseE2eAttachmentMeta(attachment['e2eMeta'] ?? attachment['e2e_meta']);
  final metaMime = (meta?['mime'] ?? '').toString().toLowerCase();
  final contentType = (attachment['contentType'] ?? attachment['content_type'] ?? metaMime)
      .toString()
      .toLowerCase();
  final filename = (attachment['filename'] ?? '').toString().toLowerCase();
  if (contentType.startsWith('audio/')) return true;
  return filename.endsWith('.m4a')
      || filename.endsWith('.wav')
      || filename.endsWith('.webm')
      || filename.endsWith('.aac')
      || filename.endsWith('.ogg')
      || filename.contains('voice-');
}

int parseE2eDurationSec(Map<String, dynamic> attachment) {
  final meta = parseE2eAttachmentMeta(attachment['e2eMeta'] ?? attachment['e2e_meta']);
  final fromMeta = int.tryParse('${meta?['durationSec'] ?? ''}') ?? 0;
  if (fromMeta > 0) return fromMeta;
  return int.tryParse('${attachment['durationSec'] ?? attachment['duration_sec'] ?? ''}') ?? 0;
}
