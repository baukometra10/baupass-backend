import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../../core/session_store.dart';
import '../../services/chat_repository.dart';
import 'chat_location_helpers.dart';

enum ChatMediaKind { image, voice, file }

class ChatMediaItem {
  ChatMediaItem({
    required this.id,
    required this.messageId,
    required this.filename,
    required this.kind,
    this.contentType = '',
    this.e2eMeta = '',
    this.createdAt = '',
  });

  final String id;
  final String messageId;
  final String filename;
  final String contentType;
  final String e2eMeta;
  final String createdAt;
  final ChatMediaKind kind;
}

List<ChatMediaItem> collectChatMediaItems(List<Map<String, dynamic>> messages) {
  final items = <ChatMediaItem>[];
  for (final msg in messages) {
    final attachments = msg['attachments'];
    if (attachments is! List) continue;
    for (final raw in attachments) {
      if (raw is! Map) continue;
      final att = Map<String, dynamic>.from(raw);
      final id = (att['id'] ?? '').toString();
      if (id.isEmpty) continue;
      final filename = (att['filename'] ?? 'file').toString();
      final contentType = (att['contentType'] ?? att['content_type'] ?? '').toString();
      final e2eMeta = (att['e2eMeta'] ?? att['e2e_meta'] ?? '').toString();
      items.add(
        ChatMediaItem(
          id: id,
          messageId: (msg['id'] ?? '').toString(),
          filename: filename,
          contentType: contentType,
          e2eMeta: e2eMeta,
          createdAt: (msg['createdAt'] ?? msg['created_at'] ?? '').toString(),
          kind: _kindForAttachment(filename, contentType, e2eMeta),
        ),
      );
    }
  }
  return items.reversed.toList();
}

ChatMediaKind _kindForAttachment(String filename, String contentType, String e2eMeta) {
  final mime = contentType.toLowerCase();
  final lower = filename.toLowerCase();
  if (mime.startsWith('audio/') ||
      lower.endsWith('.m4a') ||
      lower.endsWith('.webm') ||
      lower.endsWith('.wav') ||
      lower.endsWith('.aac') ||
      lower.startsWith('voice-')) {
    return ChatMediaKind.voice;
  }
  if (mime.startsWith('image/') ||
      lower.endsWith('.jpg') ||
      lower.endsWith('.jpeg') ||
      lower.endsWith('.png') ||
      lower.endsWith('.webp') ||
      lower.endsWith('.gif')) {
    return ChatMediaKind.image;
  }
  if (e2eMeta.contains('"mime":"audio/')) return ChatMediaKind.voice;
  if (e2eMeta.contains('"mime":"image/')) return ChatMediaKind.image;
  return ChatMediaKind.file;
}

Future<void> showChatMediaGallery({
  required BuildContext context,
  required List<Map<String, dynamic>> messages,
  required WorkerSession session,
  required ChatRepository chat,
  required Future<void> Function(String messageId) onDeleteMessage,
  required Future<void> Function(ChatMediaItem item) onOpenItem,
}) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: const Color(0xFF0B141A),
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
    ),
    builder: (context) {
      return _ChatMediaGallerySheet(
        messages: messages,
        session: session,
        chat: chat,
        onDeleteMessage: onDeleteMessage,
        onOpenItem: onOpenItem,
      );
    },
  );
}

class _ChatMediaGallerySheet extends StatefulWidget {
  const _ChatMediaGallerySheet({
    required this.messages,
    required this.session,
    required this.chat,
    required this.onDeleteMessage,
    required this.onOpenItem,
  });

  final List<Map<String, dynamic>> messages;
  final WorkerSession session;
  final ChatRepository chat;
  final Future<void> Function(String messageId) onDeleteMessage;
  final Future<void> Function(ChatMediaItem item) onOpenItem;

  @override
  State<_ChatMediaGallerySheet> createState() => _ChatMediaGallerySheetState();
}

class _ChatMediaGallerySheetState extends State<_ChatMediaGallerySheet> {
  int _tab = 0;

  List<ChatMediaItem> get _all => collectChatMediaItems(widget.messages);

  List<ChatMediaItem> get _visible {
    return switch (_tab) {
      1 => _all.where((item) => item.kind == ChatMediaKind.image).toList(),
      2 => _all.where((item) => item.kind == ChatMediaKind.voice).toList(),
      3 => _all.where((item) => item.kind == ChatMediaKind.file).toList(),
      _ => _all,
    };
  }

  @override
  Widget build(BuildContext context) {
    final height = MediaQuery.sizeOf(context).height * 0.82;
    final items = _visible;
    return SizedBox(
      height: height,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(8, 8, 8, 0),
            child: Row(
              children: [
                IconButton(
                  onPressed: () => Navigator.of(context).pop(),
                  icon: const Icon(Icons.close, color: Color(0xFFE9EDEF)),
                ),
                const Expanded(
                  child: Text(
                    'Medien',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Color(0xFFE9EDEF), fontWeight: FontWeight.w700, fontSize: 17),
                  ),
                ),
                const SizedBox(width: 48),
              ],
            ),
          ),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            child: Row(
              children: [
                for (var i = 0; i < 4; i++)
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: ChoiceChip(
                      label: Text(['Alle', 'Fotos', 'Sprache', 'Dateien'][i]),
                      selected: _tab == i,
                      onSelected: (_) => setState(() => _tab = i),
                      selectedColor: const Color(0xFF00A884).withValues(alpha: 0.25),
                      labelStyle: TextStyle(
                        color: _tab == i ? Colors.white : const Color(0xFFE9EDEF),
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
              ],
            ),
          ),
          Expanded(
            child: items.isEmpty
                ? const Center(
                    child: Text(
                      'Keine Medien in dieser Unterhaltung.',
                      style: TextStyle(color: Color(0xFF8696A0)),
                    ),
                  )
                : GridView.builder(
                    padding: const EdgeInsets.all(12),
                    gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                      crossAxisCount: 3,
                      crossAxisSpacing: 8,
                      mainAxisSpacing: 8,
                      childAspectRatio: 0.82,
                    ),
                    itemCount: items.length,
                    itemBuilder: (context, index) {
                      final item = items[index];
                      return _GalleryTile(
                        item: item,
                        session: widget.session,
                        chat: widget.chat,
                        onOpen: () async {
                          Navigator.of(context).pop();
                          await widget.onOpenItem(item);
                        },
                        onDelete: item.messageId.isEmpty
                            ? null
                            : () async {
                                final ok = await showDialog<bool>(
                                  context: context,
                                  builder: (ctx) => AlertDialog(
                                    title: const Text('Medium entfernen?'),
                                    content: const Text('Die Nachricht mit diesem Medium wird gelöscht.'),
                                    actions: [
                                      TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Abbrechen')),
                                      FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Entfernen')),
                                    ],
                                  ),
                                );
                                if (ok == true) {
                                  await widget.onDeleteMessage(item.messageId);
                                  if (context.mounted) Navigator.of(context).pop();
                                }
                              },
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}

class _GalleryTile extends StatefulWidget {
  const _GalleryTile({
    required this.item,
    required this.session,
    required this.chat,
    required this.onOpen,
    this.onDelete,
  });

  final ChatMediaItem item;
  final WorkerSession session;
  final ChatRepository chat;
  final VoidCallback onOpen;
  final Future<void> Function()? onDelete;

  @override
  State<_GalleryTile> createState() => _GalleryTileState();
}

class _GalleryTileState extends State<_GalleryTile> {
  Uint8List? _thumb;
  bool _loadingThumb = false;

  @override
  void initState() {
    super.initState();
    if (widget.item.kind == ChatMediaKind.image) _loadThumb();
  }

  Future<void> _loadThumb() async {
    setState(() => _loadingThumb = true);
    try {
      final bytes = await widget.chat.downloadAttachment(
        session: widget.session,
        attachmentId: widget.item.id,
        e2eMeta: widget.item.e2eMeta,
        filename: widget.item.filename,
      );
      if (!mounted) return;
      setState(() {
        _thumb = bytes;
        _loadingThumb = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _loadingThumb = false);
    }
  }

  IconData get _icon {
    return switch (widget.item.kind) {
      ChatMediaKind.image => Icons.image_outlined,
      ChatMediaKind.voice => Icons.mic,
      ChatMediaKind.file => Icons.attach_file,
    };
  }

  @override
  Widget build(BuildContext context) {
    return Material(
      color: const Color(0xFF1F2C34),
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        onTap: widget.onOpen,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Expanded(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(8),
                  child: widget.item.kind == ChatMediaKind.image
                      ? (_loadingThumb
                          ? const Center(child: SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)))
                          : (_thumb != null
                              ? Image.memory(_thumb!, fit: BoxFit.cover, width: double.infinity, height: double.infinity)
                              : Center(child: Icon(_icon, size: 28, color: const Color(0xFF8696A0)))))
                      : Center(child: Icon(_icon, size: 28, color: const Color(0xFF8696A0))),
                ),
              ),
              const SizedBox(height: 6),
              Text(
                widget.item.filename,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: Color(0xFFE9EDEF), fontSize: 11),
              ),
              if (widget.onDelete != null)
                TextButton(
                  onPressed: () => widget.onDelete!(),
                  style: TextButton.styleFrom(
                    padding: EdgeInsets.zero,
                    minimumSize: const Size(0, 28),
                    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  ),
                  child: const Text('Entfernen', style: TextStyle(fontSize: 11)),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
