import 'package:baupass_worker/features/chat/chat_message_prefs.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('applyServerPrefs hydrates pin and star', () {
    final state = ChatMessagePrefsState();
    state.applyServerPrefs({
      'msg-1': {'pinnedAt': '2026-07-16T10:00:00Z', 'starred': true},
      'msg-2': {'pinnedAt': null, 'starred': false},
    });
    expect(state.isPinned('msg-1'), isTrue);
    expect(state.isStarred('msg-1'), isTrue);
    expect(state.isPinned('msg-2'), isFalse);
    expect(state.isStarred('msg-2'), isFalse);
  });

  test('togglePin and toggleStar update local state', () {
    final state = ChatMessagePrefsState();
    expect(state.togglePin('a'), isTrue);
    expect(state.isPinned('a'), isTrue);
    expect(state.togglePin('a'), isFalse);
    expect(state.isPinned('a'), isFalse);

    expect(state.toggleStar('b'), isTrue);
    expect(state.isStarred('b'), isTrue);
    expect(state.toggleStar('b'), isFalse);
  });

  test('pinnedIdsSorted returns newest first', () {
    final state = ChatMessagePrefsState();
    state.pinnedAt['old'] = 100;
    state.pinnedAt['new'] = 200;
    expect(state.pinnedIdsSorted(), ['new', 'old']);
  });
}
