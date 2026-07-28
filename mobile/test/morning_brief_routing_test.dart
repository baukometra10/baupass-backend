import 'package:baupass_worker/core/app_strings.dart';
import 'package:baupass_worker/services/deep_link_service.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('morning brief action strings exist in DE', () {
    expect(t('morningBriefTitle'), isNot(equals('morningBriefTitle')));
    expect(t('morningGoCheckin'), isNotEmpty);
    expect(t('morningGoChat'), isNotEmpty);
    expect(t('morningGoDocs'), isNotEmpty);
  });

  test('baupass://app/home opens pass tab', () {
    final route = DeepLinkService.appRouteFromUri(Uri.parse('baupass://app/home'));
    expect(route?.tabIndex, 0);
    expect(route?.openChat, isNot(true));
  });

  test('baupass://app/chat?missed=1 opens chat without ring wake', () {
    final route = DeepLinkService.appRouteFromUri(
      Uri.parse('baupass://app/chat?missed=1&callId=vc-final'),
    );
    expect(route?.openChat, isTrue);
    expect(route?.missedCallId, 'vc-final');
    expect(route?.incomingCallId, isNull);
  });
}
