import 'package:flutter/material.dart';

import 'app.dart';
import 'firebase_bootstrap.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await FirebaseBootstrap.initialize();
  runApp(const WorkerApp());
}
