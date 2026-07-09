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

class _QrScanPanelState extends State<QrScanPanel> {
  final MobileScannerController _controller = MobileScannerController(
    detectionSpeed: DetectionSpeed.normal,
    facing: CameraFacing.back,
    formats: const [BarcodeFormat.qrCode],
  );
  bool _handled = false;

  @override
  void dispose() {
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
    if (payload == null) return;
    _handled = true;
    await widget.onScanned(payload);
    if (mounted) {
      await Future<void>.delayed(const Duration(milliseconds: 900));
      _handled = false;
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
                'QR-Code des Administrators in den Rahmen halten',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: Colors.white,
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
