package com.baupass.hce

import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {
    private val apiClient = ApiClient()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        val baseUrlInput = findViewById<EditText>(R.id.baseUrlInput)
        val sessionTokenInput = findViewById<EditText>(R.id.sessionTokenInput)
        val deviceIdInput = findViewById<EditText>(R.id.deviceIdInput)
        val bootstrapBtn = findViewById<Button>(R.id.bootstrapBtn)
        val statusView = findViewById<TextView>(R.id.statusView)

        // Restore last successful config for fast restart and auto-refresh.
        baseUrlInput.setText(HceTokenStore.getBaseUrl(this))
        sessionTokenInput.setText(HceTokenStore.getWorkerToken(this))
        deviceIdInput.setText(HceTokenStore.getDeviceId(this))

        if (HceTokenStore.hasBootstrapConfig(this)) {
            HceBootstrapScheduler.schedulePeriodic(this)
        }

        if (HceTokenStore.hasBootstrapConfig(this) && !HceTokenStore.isTokenValid(this)) {
            statusView.text = "Status: Token abgelaufen, erneuere im Hintergrund..."
            HceBootstrapScheduler.triggerNow(this)
        }

        bootstrapBtn.setOnClickListener {
            val baseUrl = baseUrlInput.text?.toString()?.trim().orEmpty()
            val workerToken = sessionTokenInput.text?.toString()?.trim().orEmpty()
            val deviceId = deviceIdInput.text?.toString()?.trim().orEmpty()

            if (baseUrl.isBlank() || workerToken.isBlank() || deviceId.isBlank()) {
                statusView.text = "Status: Bitte Backend URL, Session Token und Device ID ausfüllen."
                return@setOnClickListener
            }

            statusView.text = "Status: Lade HCE Bootstrap..."
            Thread {
                try {
                    val existingSecret = HceTokenStore.getDeviceSecret(this)
                    val deviceSecret = if (existingSecret.isBlank()) {
                        val registerResult = apiClient.registerHceDevice(baseUrl, workerToken, deviceId)
                        HceTokenStore.saveDeviceSecret(this, registerResult.deviceSecret)
                        registerResult.deviceSecret
                    } else {
                        existingSecret
                    }

                    val result = apiClient.fetchHceBootstrap(baseUrl, workerToken, deviceId, deviceSecret)
                    val expiresAtMs = System.currentTimeMillis() + (result.remainingSec.coerceAtLeast(20) * 1000L)
                    HceTokenStore.save(this, result.payloadToken, expiresAtMs, result.aid)
                    HceTokenStore.saveBootstrapConfig(this, baseUrl, workerToken, deviceId)
                    HceBootstrapScheduler.schedulePeriodic(this)
                    runOnUiThread {
                        statusView.text = "Status: Aktiv. AID=${result.aid}, Badge=${result.badgeId}, gueltig ${result.remainingSec}s"
                    }
                } catch (ex: Exception) {
                    runOnUiThread {
                        statusView.text = "Status: Fehler beim Bootstrap: ${ex.message}"
                    }
                }
            }.start()
        }
    }
}
