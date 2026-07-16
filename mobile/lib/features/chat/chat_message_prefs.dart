/// In-memory pin/star state for a chat thread (synced via worker message-prefs API).
class ChatMessagePrefsState {
  ChatMessagePrefsState();

  final Map<String, int> pinnedAt = {};
  final Set<String> starred = {};

  bool isPinned(String messageId) => pinnedAt.containsKey(messageId.trim());

  bool isStarred(String messageId) => starred.contains(messageId.trim());

  List<String> pinnedIdsSorted() {
    final entries = pinnedAt.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    return entries.map((e) => e.key).toList();
  }

  void applyServerPrefs(Map<String, dynamic> prefs) {
    pinnedAt.clear();
    starred.clear();
    prefs.forEach((messageId, raw) {
      final id = messageId.trim();
      if (id.isEmpty || raw is! Map) return;
      final pinnedAtRaw = raw['pinnedAt'] ?? raw['pinned_at'];
      if (pinnedAtRaw != null && '$pinnedAtRaw'.trim().isNotEmpty) {
        final ts = DateTime.tryParse('$pinnedAtRaw')?.millisecondsSinceEpoch ?? DateTime.now().millisecondsSinceEpoch;
        pinnedAt[id] = ts;
      }
      if (raw['starred'] == true) starred.add(id);
    });
  }

  bool togglePin(String messageId) {
    final id = messageId.trim();
    if (id.isEmpty) return false;
    if (pinnedAt.containsKey(id)) {
      pinnedAt.remove(id);
      return false;
    }
    pinnedAt[id] = DateTime.now().millisecondsSinceEpoch;
    return true;
  }

  bool toggleStar(String messageId) {
    final id = messageId.trim();
    if (id.isEmpty) return false;
    if (starred.contains(id)) {
      starred.remove(id);
      return false;
    }
    starred.add(id);
    return true;
  }
}
