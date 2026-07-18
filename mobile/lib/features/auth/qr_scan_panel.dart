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
    this.onRequestManualLogin,
  });

  final QrScanHandler onScanned;
  final bool busy;
  final VoidCallback? onRequestManualLogin;

  @override
  State<QrScanPanel> createState() => _QrScanPanelState();
}

class _QrScanPanelState extends State<QrScanPanel> with WidgetsBindingObserver {
  // autoStart must stay false — explicit start() + default autoStart races and
  // surfaces as "Kamera-Fehler — App neu starten…" (controllerAlreadyInitialized).
  late final MobileScannerController _controller = MobileScannerController(
    autoStart: false,
    detectionSpeed: DetectionSpeed.normal,
    facing: CameraFacing.back,
    formats: const [BarcodeFormat.qrCode],
  );
  bool _handled = false;
  bool _starting = false;
  String? _cameraError;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _safeStart();
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Permission dialogs also emit lifecycle events — guard before start/stop.
    if (!_controller.value.isInitialized &&
        _controller.value.error?.errorCode == MobileScannerErrorCode.permissionDenied) {
      return;
    }
    if (state == AppLifecycleState.resumed) {
      _safeStart();
      return;
    }
    if (state == AppLifecycleState.inactive || state == AppLifecycleState.paused) {
      _safeStop();
    }
  }

  Future<void> _safeStart() async {
    if (!mounted || _starting) return;
    if (_controller.value.isRunning) return;
    _starting = true;
    try {
      await _controller.start();
      if (mounted) setState(() => _cameraError = null);
    } on MobileScannerException catch (err) {
      if (err.errorCode == MobileScannerErrorCode.controllerAlreadyInitialized) {
        // Benign race — camera is already up.
        if (mounted) setState(() => _cameraError = null);
        return;
      }
      if (mounted) setState(() => _cameraError = _errorText(err));
    } catch (_) {
      if (mounted) {
        setState(() => _cameraError = 'Kamera-Fehler — erneut versuchen oder Manuell-Login nutzen.');
      }
    } finally {
      _starting = false;
    }
  }

  Future<void> _safeStop() async {
    try {
      if (_controller.value.isRunning) {
        await _controller.stop();
      }
    } catch (_) {}
  }

  Future<void> _retryCamera() async {
    setState(() => _cameraError = null);
    try {
      await _controller.stop();
    } catch (_) {}
    await Future<void>.delayed(const Duration(milliseconds: 250));
    await _safeStart();
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
        return 'Kamera blockiert — in den Handy-Einstellungen für SUPPIX erlauben, dann „Erneut versuchen“.';
      case MobileScannerErrorCode.unsupported:
        return 'Kamera auf diesem Gerät nicht unterstützt — bitte Manuell-Login nutzen.';
      case MobileScannerErrorCode.controllerAlreadyInitialized:
        return '';
      case MobileScannerErrorCode.controllerDisposed:
        return 'Kamera wurde beendet — „Erneut versuchen“ tippen.';
      case MobileScannerErrorCode.controllerUninitialized:
        return 'Kamera startet… kurz warten oder „Erneut versuchen“.';
      default:
        return 'Kamera-Fehler — „Erneut versuchen“ oder Manuell-Login (Badge + PIN) nutzen.';
    }
  }

  Widget _errorOverlay(String message) {
    return ColoredBox(
      color: Colors.black87,
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                message,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.white, fontSize: 16),
              ),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: _retryCamera,
                child: const Text('Erneut versuchen'),
              ),
              if (widget.onRequestManualLogin != null) ...[
                const SizedBox(height: 8),
                TextButton(
                  onPressed: widget.onRequestManualLogin,
                  child: const Text('Manuell anmelden', style: TextStyle(color: Colors.white)),
                ),
              ],
            ],
          ),
        ),
      ),
    );
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
                final text = _errorText(error);
                if (text.isEmpty) {
                  // Already-started is not fatal — keep trying preview.
                  return child ?? const ColoredBox(color: Colors.black);
                }
                return _errorOverlay(text);
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
            if (_cameraError != null && _cameraError!.isNotEmpty)
              Positioned(
                left: 16,
                right: 16,
                bottom: 56,
                child: Wrap(
                  alignment: WrapAlignment.center,
                  spacing: 8,
                  children: [
                    TextButton(
                      onPressed: _retryCamera,
                      child: const Text('Erneut versuchen', style: TextStyle(color: Colors.white)),
                    ),
                    if (widget.onRequestManualLogin != null)
                      TextButton(
                        onPressed: widget.onRequestManualLogin,
                        child: const Text('Manuell', style: TextStyle(color: Colors.white)),
                      ),
                  ],
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
