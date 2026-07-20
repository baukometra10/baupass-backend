import 'package:flutter/material.dart';

import 'app.dart';
import 'firebase_bootstrap.dart';
import 'services/push_background_handler.dart';
import 'package:firebase_messaging/firebase_messaging.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await FirebaseBootstrap.initialize();
  FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);
  runApp(const WorkerApp());
}
