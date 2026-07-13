import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../core/qr_activation_parser.dart';

typedef QrScanHandler = Future<void> Function(QrActivationPayload payload);

/// Camera-style QR viewfinder for worker activation.
class QrScanPanel extends StatefulWidget {
  const QrScanPanel({
    super.key,
    required this.onScanned,
    this.busy = false,
  });

  final QrScanHandler onScanned;
  final bool busy;

  @override
  State<QrScanPanel> createState() => _QrScanPanelState();
}

class _QrScanPanelState extends State<QrScanPanel> with WidgetsBindingObserver {
  final MobileScannerController _controller = MobileScannerController(
    detectionSpeed: DetectionSpeed.normal,
    facing: CameraFacing.back,
    formats: const [BarcodeFormat.qrCode],
  );
  bool _handled = false;
  String? _cameraError;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    // Start explicitly: some devices return a black camera preview until start() is called after first render.
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      try {
        await _controller.start();
      } catch (_) {
        // errorBuilder will handle permission/unsupported; ignore here.
      }
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // After install / returning from settings, the app resumes and the camera must be restarted.
    if (state == AppLifecycleState.resumed) {
      _controller.start().catchError((_) {});
      return;
    }
    if (state == AppLifecycleState.inactive || state == AppLifecycleState.paused) {
      _controller.stop().catchError((_) {});
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _controller.dispose();
    super.dispose();
  }

  Future<void> _onDetect(BarcodeCapture capture) async {
    if (widget.busy || _handled) return;
    final raw = capture.barcodes
        .map((b) => (b.rawValue ?? '').trim())
        .firstWhere((v) => v.isNotEmpty, orElse: () => '');
    if (raw.isEmpty) return;
    final payload = QrActivationParser.parse(raw);
    if (payload == null) {
      if (mounted) {
        setState(() => _cameraError = 'QR-Code nicht erkannt — Admin-QR erneut scannen.');
      }
      return;
    }
    _handled = true;
    setState(() => _cameraError = null);
    await widget.onScanned(payload);
    if (mounted) {
      await Future<void>.delayed(const Duration(milliseconds: 900));
      _handled = false;
    }
  }

  String _errorText(MobileScannerException error) {
    switch (error.errorCode) {
      case MobileScannerErrorCode.permissionDenied:
        return 'Kamera blockiert — in Einstellungen für SUPPIX erlauben.';
      case MobileScannerErrorCode.unsupported:
        return 'Kamera auf diesem Gerät nicht unterstützt.';
      default:
        return 'Kamera-Fehler — App neu starten oder Manuell-Login nutzen.';
    }
  }

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.sizeOf(context);
    final frame = size.shortestSide * 0.68;

    return ClipRRect(
      borderRadius: BorderRadius.circular(24),
      child: AspectRatio(
        aspectRatio: 3 / 4,
        child: Stack(
          fit: StackFit.expand,
          children: [
            MobileScanner(
              controller: _controller,
              onDetect: _onDetect,
              errorBuilder: (context, error, child) {
                return ColoredBox(
                  color: Colors.black87,
                  child: Center(
                    child: Padding(
                      padding: const EdgeInsets.all(20),
                      child: Text(
                        _errorText(error),
                        textAlign: TextAlign.center,
                        style: const TextStyle(color: Colors.white, fontSize: 16),
                      ),
                    ),
                  ),
                );
              },
            ),
            Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    Colors.black.withValues(alpha: 0.55),
                    Colors.transparent,
                    Colors.black.withValues(alpha: 0.65),
                  ],
                  stops: const [0, 0.45, 1],
                ),
              ),
            ),
            Center(
              child: Container(
                width: frame,
                height: frame,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: Colors.white, width: 3),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.35),
                      blurRadius: 18,
                    ),
                  ],
                ),
              ),
            ),
            Positioned(
              left: 16,
              right: 16,
              bottom: 16,
              child: Text(
                _cameraError ??
                    'QR-Code des Administrators in den Rahmen halten',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: _cameraError != null ? Colors.orangeAccent : Colors.white,
                      fontWeight: FontWeight.w600,
                      shadows: const [Shadow(color: Colors.black54, blurRadius: 8)],
                    ),
              ),
            ),
            if (widget.busy)
              Container(
                color: Colors.black45,
                child: const Center(child: CircularProgressIndicator()),
              ),
          ],
        ),
      ),
    );
  }
}
