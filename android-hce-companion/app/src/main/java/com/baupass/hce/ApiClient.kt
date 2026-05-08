package com.baupass.hce

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.UUID
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

class ApiClient {
    private val client = OkHttpClient()

    data class RegisterResult(
        val deviceId: String,
        val deviceSecret: String
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
        val payload = JSONObject()
            .put("deviceId", deviceId)
            .put("platform", "android")
            .put("appVersion", "1.0.0")
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
            val deviceSecret = json.optString("deviceSecret", "")
            if (resultDeviceId.isBlank() || deviceSecret.isBlank()) {
                throw IllegalStateException("Backend returned invalid register payload")
            }
            return RegisterResult(resultDeviceId, deviceSecret)
        }
    }

    fun fetchHceBootstrap(baseUrl: String, workerSessionToken: String, deviceId: String, deviceSecret: String): BootstrapResult {
        val root = baseUrl.trimEnd('/')
        val url = "$root/api/worker-app/hce/bootstrap"
        val nonce = UUID.randomUUID().toString().replace("-", "")
        val clientTs = System.currentTimeMillis().toString()
        val signature = signDevicePayload(deviceSecret, deviceId, nonce, clientTs)
        val payload = JSONObject()
            .put("deviceId", deviceId)
            .put("platform", "android")
            .put("appVersion", "1.0.0")
            .put("nonce", nonce)
            .put("clientTs", clientTs)
            .put("deviceSignature", signature)
            .toString()
        val requestBody = payload.toRequestBody("application/json; charset=utf-8".toMediaType())

        val request = Request.Builder()
            .url(url)
            .addHeader("Authorization", "Bearer $workerSessionToken")
            .addHeader("X-HCE-Device-Signature", signature)
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

    private fun signDevicePayload(deviceSecret: String, deviceId: String, nonce: String, clientTs: String): String {
        val payload = "$deviceId|$nonce|$clientTs"
        val mac = Mac.getInstance("HmacSHA256")
        val keySpec = SecretKeySpec(deviceSecret.toByteArray(Charsets.UTF_8), "HmacSHA256")
        mac.init(keySpec)
        val digest = mac.doFinal(payload.toByteArray(Charsets.UTF_8))
        return digest.joinToString("") { "%02x".format(it) }
    }
}
