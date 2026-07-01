import 'package:flutter_test/flutter_test.dart';

import 'package:baupass_worker/app.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('WorkerApp shows login title after bootstrap', (tester) async {
    await tester.pumpWidget(const WorkerApp());
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Mitarbeiter'), findsOneWidget);
  });
}
