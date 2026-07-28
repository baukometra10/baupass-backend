import 'package:baupass_worker/services/deep_link_service.dart';
import 'package:baupass_worker/services/push_navigation.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('voice-call-missed opens chat without incoming wake id', () {
    final route = PushNavigation.routeFromData({
      'tag': 'voice-call-missed',
      'callId': 'vc-1',
      'type': 'voice_call_missed',
    });
    expect(route, isNotNull);
    expect(route!.openChat, isTrue);
    expect(route.tabIndex, 3);
    expect(route.missedCallId, 'vc-1');
    expect(route.incomingCallId, isNull);
    expect(route.requestCallback, isFalse);
  });

  test('type voice_call_missed without tag still routes', () {
    final route = PushNavigation.routeFromData({
      'type': 'voice_call_missed',
      'callId': 'vc-2',
    });
    expect(route?.missedCallId, 'vc-2');
    expect(route?.openChat, isTrue);
  });

  test('deeplink chat missed+callback requests auto callback', () {
    final route = DeepLinkService.appRouteFromUri(
      Uri.parse('baupass://app/chat?callId=vc-3&missed=1&callback=1'),
    );
    expect(route?.missedCallId, 'vc-3');
    expect(route?.requestCallback, isTrue);
    expect(route?.openChat, isTrue);
  });

  test('route field in push payload is honored', () {
    final route = PushNavigation.routeFromData({
      'route': 'baupass://app/chat?callId=vc-4&missed=1',
      'tag': 'unrelated',
    });
    expect(route?.missedCallId, 'vc-4');
  });
}
