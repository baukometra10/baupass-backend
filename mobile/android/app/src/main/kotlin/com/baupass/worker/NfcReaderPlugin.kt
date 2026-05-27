package com.baupass.worker

import android.app.Activity
import android.nfc.NfcAdapter
import android.nfc.Tag
import android.os.Bundle
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.embedding.engine.plugins.activity.ActivityAware
import io.flutter.embedding.engine.plugins.activity.ActivityPluginBinding
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel

/**
 * Reads NFC tag UID via Android Reader Mode and returns hex UID to Flutter.
 */
class NfcReaderPlugin : FlutterPlugin, MethodChannel.MethodCallHandler, ActivityAware, NfcAdapter.ReaderCallback {

    private lateinit var channel: MethodChannel
    private var activity: Activity? = null
    private var nfcAdapter: NfcAdapter? = null
    private var pendingResult: MethodChannel.Result? = null

    override fun onAttachedToEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        channel = MethodChannel(binding.binaryMessenger, "com.baupass.worker/nfc")
        channel.setMethodCallHandler(this)
    }

    override fun onDetachedFromEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        channel.setMethodCallHandler(null)
        stopReaderMode()
    }

    override fun onAttachedToActivity(binding: ActivityPluginBinding) {
        activity = binding.activity
        nfcAdapter = NfcAdapter.getDefaultAdapter(activity)
        binding.addOnUserLeaveHintListener { cancelScan("scan_cancelled", "User left the app during NFC scan.") }
    }

    override fun onDetachedFromActivityForConfigChanges() {
        onDetachedFromActivity()
    }

    override fun onReattachedToActivityForConfigChanges(binding: ActivityPluginBinding) {
        onAttachedToActivity(binding)
    }

    override fun onDetachedFromActivity() {
        cancelScan("scan_cancelled", "Activity detached.")
        activity = null
        nfcAdapter = null
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "isAvailable" -> {
                val adapter = nfcAdapter
                result.success(adapter != null && adapter.isEnabled)
            }
            "scanTag" -> {
                if (pendingResult != null) {
                    result.error("scan_in_progress", "NFC scan already in progress.", null)
                    return
                }
                val adapter = nfcAdapter
                val act = activity
                if (adapter == null || act == null) {
                    result.error("nfc_unavailable", "NFC adapter not available.", null)
                    return
                }
                if (!adapter.isEnabled) {
                    result.error("nfc_unavailable", "NFC is disabled. Enable it in settings.", null)
                    return
                }
                pendingResult = result
                val flags = NfcAdapter.FLAG_READER_NFC_A or
                    NfcAdapter.FLAG_READER_NFC_B or
                    NfcAdapter.FLAG_READER_SKIP_NDEF_CHECK
                adapter.enableReaderMode(act, this, flags, Bundle())
            }
            else -> result.notImplemented()
        }
    }

    override fun onTagDiscovered(tag: Tag?) {
        val result = pendingResult ?: return
        pendingResult = null
        stopReaderMode()
        if (tag == null) {
            result.error("scan_failed", "Empty NFC tag.", null)
            return
        }
        val uid = tag.id?.toHex() ?: ""
        if (uid.isEmpty()) {
            result.error("scan_failed", "Could not read tag UID.", null)
            return
        }
        result.success(
            mapOf(
                "uid" to uid,
                "platform" to "android",
            )
        )
    }

    private fun stopReaderMode() {
        val adapter = nfcAdapter
        val act = activity
        if (adapter != null && act != null) {
            try {
                adapter.disableReaderMode(act)
            } catch (_: Exception) {
            }
        }
    }

    private fun cancelScan(code: String, message: String) {
        val result = pendingResult ?: return
        pendingResult = null
        stopReaderMode()
        result.error(code, message, null)
    }

    private fun ByteArray.toHex(): String =
        joinToString("") { byte -> "%02X".format(byte) }
}
