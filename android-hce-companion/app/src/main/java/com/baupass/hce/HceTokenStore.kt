package com.baupass.hce

import android.content.Context

object HceTokenStore {
    private const val PREFS = "baupass_hce_prefs"
    private const val KEY_TOKEN = "payload_token"
    private const val KEY_EXPIRES_AT_MS = "expires_at_ms"
    private const val KEY_AID = "aid"
    private const val KEY_BASE_URL = "base_url"
    private const val KEY_WORKER_TOKEN = "worker_token"
    private const val KEY_WORKER_TOKEN_CT = "worker_token_ct"
    private const val KEY_WORKER_TOKEN_IV = "worker_token_iv"
    private const val KEY_DEVICE_ID = "device_id"
    private const val KEY_DEVICE_SECRET_CT = "device_secret_ct"
    private const val KEY_DEVICE_SECRET_IV = "device_secret_iv"

    fun save(context: Context, token: String, expiresAtMs: Long, aid: String) {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        prefs.edit()
            .putString(KEY_TOKEN, token)
            .putLong(KEY_EXPIRES_AT_MS, expiresAtMs)
            .putString(KEY_AID, aid)
            .apply()
    }

    fun getToken(context: Context): String {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        return prefs.getString(KEY_TOKEN, "") ?: ""
    }

    fun getAid(context: Context): String {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        return prefs.getString(KEY_AID, "F0010203040506") ?: "F0010203040506"
    }

    fun isTokenValid(context: Context): Boolean {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val expiresAt = prefs.getLong(KEY_EXPIRES_AT_MS, 0L)
        val token = prefs.getString(KEY_TOKEN, "") ?: ""
        return token.isNotBlank() && System.currentTimeMillis() < expiresAt
    }

    fun getTokenExpiresAtMs(context: Context): Long {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        return prefs.getLong(KEY_EXPIRES_AT_MS, 0L)
    }

    fun saveBootstrapConfig(context: Context, baseUrl: String, workerToken: String, deviceId: String) {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val (tokenCt, tokenIv) = SecurePrefsCrypto.encrypt(workerToken.trim())
        prefs.edit()
            .putString(KEY_BASE_URL, baseUrl.trim())
            .putString(KEY_WORKER_TOKEN_CT, tokenCt)
            .putString(KEY_WORKER_TOKEN_IV, tokenIv)
            .remove(KEY_WORKER_TOKEN)
            .putString(KEY_DEVICE_ID, deviceId.trim())
            .apply()
    }

    fun hasBootstrapConfig(context: Context): Boolean {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val baseUrl = prefs.getString(KEY_BASE_URL, "") ?: ""
        val workerToken = getWorkerToken(context)
        val deviceId = prefs.getString(KEY_DEVICE_ID, "") ?: ""
        return baseUrl.isNotBlank() && workerToken.isNotBlank() && deviceId.isNotBlank()
    }

    fun getBaseUrl(context: Context): String {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        return prefs.getString(KEY_BASE_URL, "") ?: ""
    }

    fun getWorkerToken(context: Context): String {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val tokenCt = prefs.getString(KEY_WORKER_TOKEN_CT, "") ?: ""
        val tokenIv = prefs.getString(KEY_WORKER_TOKEN_IV, "") ?: ""
        if (tokenCt.isNotBlank() && tokenIv.isNotBlank()) {
            return try {
                SecurePrefsCrypto.decrypt(tokenCt, tokenIv)
            } catch (_: Exception) {
                ""
            }
        }

        // Backward-compat for previously unencrypted storage.
        return prefs.getString(KEY_WORKER_TOKEN, "") ?: ""
    }

    fun getDeviceId(context: Context): String {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        return prefs.getString(KEY_DEVICE_ID, "") ?: ""
    }

    fun saveDeviceSecret(context: Context, deviceSecret: String) {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val (ct, iv) = SecurePrefsCrypto.encrypt(deviceSecret.trim())
        prefs.edit()
            .putString(KEY_DEVICE_SECRET_CT, ct)
            .putString(KEY_DEVICE_SECRET_IV, iv)
            .apply()
    }

    fun getDeviceSecret(context: Context): String {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val ct = prefs.getString(KEY_DEVICE_SECRET_CT, "") ?: ""
        val iv = prefs.getString(KEY_DEVICE_SECRET_IV, "") ?: ""
        if (ct.isBlank() || iv.isBlank()) return ""
        return try {
            SecurePrefsCrypto.decrypt(ct, iv)
        } catch (_: Exception) {
            ""
        }
    }
}
