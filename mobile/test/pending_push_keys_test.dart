import 'package:baupass_worker/services/push_background_handler.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
  });

  test('pending missed voice call is one-shot', () async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(kPendingMissedVoiceCallIdKey, 'vc-cold-1');
    expect(await takePendingMissedVoiceCallId(), 'vc-cold-1');
    expect(await takePendingMissedVoiceCallId(), isNull);
  });

  test('pending missed callback is one-shot', () async {
    await persistPendingMissedCallback('vc-cb-1');
    expect(await takePendingMissedCallback(), 'vc-cb-1');
    expect(await takePendingMissedCallback(), isNull);
  });

  test('pending morning brief is one-shot', () async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(kPendingMorningBriefKey, true);
    expect(await takePendingMorningBrief(), isTrue);
    expect(await takePendingMorningBrief(), isFalse);
  });
}
