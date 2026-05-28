import CoreNFC
import Flutter
import UIKit

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    if let registrar = engineBridge.pluginRegistry.registrar(forPlugin: "NfcReaderPlugin") {
      NfcReaderPlugin.register(with: registrar)
    }
  }
}

/// Core NFC tag UID reader — returns hex UID to Flutter via MethodChannel.
/// Kept in AppDelegate.swift so CI does not need to patch project.pbxproj.
public class NfcReaderPlugin: NSObject, FlutterPlugin, NFCTagReaderSessionDelegate {
    private var pendingResult: FlutterResult?
    private var session: NFCTagReaderSession?

    public static func register(with registrar: FlutterPluginRegistrar) {
        let channel = FlutterMethodChannel(
            name: "com.baupass.worker/nfc",
            binaryMessenger: registrar.messenger()
        )
        let instance = NfcReaderPlugin()
        registrar.addMethodCallDelegate(instance, channel: channel)
    }

    public func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        switch call.method {
        case "isAvailable":
            result(NFCTagReaderSession.readingAvailable)
        case "scanTag":
            guard NFCTagReaderSession.readingAvailable else {
                result(
                    FlutterError(
                        code: "nfc_unavailable",
                        message: "NFC is not available on this device.",
                        details: nil
                    )
                )
                return
            }
            if pendingResult != nil {
                result(FlutterError(code: "scan_in_progress", message: "Scan already active.", details: nil))
                return
            }
            pendingResult = result
            session = NFCTagReaderSession(pollingOption: [.iso14443, .iso15693], delegate: self)
            session?.alertMessage = "Hold your employee card near the top of the iPhone."
            session?.begin()
        default:
            result(FlutterMethodNotImplemented)
        }
    }

    public func tagReaderSessionDidBecomeActive(_ session: NFCTagReaderSession) {}

    public func tagReaderSession(_ session: NFCTagReaderSession, didInvalidateWithError error: Error) {
        guard let result = pendingResult else { return }
        pendingResult = nil
        let nsError = error as NSError
        if nsError.domain == NFCReaderError.errorDomain,
           nsError.code == NFCReaderError.readerSessionInvalidationErrorUserCanceled.rawValue {
            result(FlutterError(code: "scan_cancelled", message: "NFC scan cancelled.", details: nil))
        } else {
            result(FlutterError(code: "scan_failed", message: error.localizedDescription, details: nil))
        }
    }

    public func tagReaderSession(_ session: NFCTagReaderSession, didDetect tags: [NFCTag]) {
        guard let tag = tags.first else { return }
        session.connect(to: tag) { [weak self] connectError in
            guard let self = self else { return }
            if let connectError = connectError {
                session.invalidate(errorMessage: connectError.localizedDescription)
                self.finishWithError(connectError.localizedDescription)
                return
            }
            let uid = Self.hexIdentifier(from: tag)
            session.invalidate()
            guard let result = self.pendingResult else { return }
            self.pendingResult = nil
            if uid.isEmpty {
                result(FlutterError(code: "scan_failed", message: "Empty UID.", details: nil))
            } else {
                result(["uid": uid, "platform": "ios"])
            }
        }
    }

    private func finishWithError(_ message: String) {
        guard let result = pendingResult else { return }
        pendingResult = nil
        result(FlutterError(code: "scan_failed", message: message, details: nil))
    }

    private static func hexIdentifier(from tag: NFCTag) -> String {
        switch tag {
        case .miFare(let miFareTag):
            return miFareTag.identifier.map { String(format: "%02X", $0) }.joined()
        case .iso7816(let iso7816Tag):
            return iso7816Tag.identifier.map { String(format: "%02X", $0) }.joined()
        case .iso15693(let iso15693Tag):
            return iso15693Tag.identifier.map { String(format: "%02X", $0) }.joined()
        case .feliCa(let feliCaTag):
            return feliCaTag.currentIDm.map { String(format: "%02X", $0) }.joined()
        @unknown default:
            return ""
        }
    }
}
