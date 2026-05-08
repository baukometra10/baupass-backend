package com.baupass.hce

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.UUID

class ApiClient {
    private val client = OkHttpClient()

    data class RegisterResult(
        val deviceId: String,
        val trustVersion: Int
    )

    data class BootstrapResult(
        val protocol: String,
        val aid: String,
        val payloadToken: String,
        val remainingSec: Int,
        val badgeId: String
    )

    fun registerHceDevice(baseUrl: String, workerSessionToken: String, deviceId: String): RegisterResult {
        val root = baseUrl.trimEnd('/')
        val url = "$root/api/worker-app/hce/device/register"
        val pubKeyB64 = DeviceKeyManager.getOrCreatePublicKeyDerB64()
        val payload = JSONObject()
            .put("deviceId", deviceId)
            .put("platform", "android")
            .put("appVersion", "1.0.0")
            .put("trustVersion", 2)
            .put("signatureAlgo", "SHA256withECDSA")
            .put("devicePublicKey", pubKeyB64)
            .toString()
        val requestBody = payload.toRequestBody("application/json; charset=utf-8".toMediaType())

        val request = Request.Builder()
            .url(url)
            .addHeader("Authorization", "Bearer $workerSessionToken")
            .post(requestBody)
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw IllegalStateException("Device register failed (${response.code}): $body")
            }
            val json = JSONObject(body)
            val resultDeviceId = json.optString("deviceId", "")
            val trustVersion = json.optInt("trustVersion", 1)
            if (resultDeviceId.isBlank()) {
                throw IllegalStateException("Backend returned invalid register payload")
            }
            return RegisterResult(resultDeviceId, trustVersion)
        }
    }

    fun fetchHceBootstrap(baseUrl: String, workerSessionToken: String, deviceId: String): BootstrapResult {
        val root = baseUrl.trimEnd('/')
        val url = "$root/api/worker-app/hce/bootstrap"
        val nonce = UUID.randomUUID().toString().replace("-", "")
        val clientTs = System.currentTimeMillis().toString()
        val payloadToSign = "$deviceId|$nonce|$clientTs"
        val signatureV2 = DeviceKeyManager.signPayloadB64(payloadToSign)
        val payload = JSONObject()
            .put("deviceId", deviceId)
            .put("platform", "android")
            .put("appVersion", "1.0.0")
            .put("nonce", nonce)
            .put("clientTs", clientTs)
            .put("deviceSignatureV2", signatureV2)
            .toString()
        val requestBody = payload.toRequestBody("application/json; charset=utf-8".toMediaType())

        val request = Request.Builder()
            .url(url)
            .addHeader("Authorization", "Bearer $workerSessionToken")
            .addHeader("X-HCE-Device-Signature-V2", signatureV2)
            .post(requestBody)
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw IllegalStateException("Bootstrap failed (${response.code}): $body")
            }
            val json = JSONObject(body)
            val protocol = json.optString("protocol", "baupass-hce-v1")
            val aid = json.optString("aid", "F0010203040506")
            val token = json.optString("payloadToken", "")
            val remainingSec = json.optInt("remainingSec", 60)
            val badgeId = json.optString("badgeId", "")
            if (token.isBlank()) {
                throw IllegalStateException("Backend returned empty payloadToken")
            }
            return BootstrapResult(protocol, aid, token, remainingSec, badgeId)
        }
    }
}
