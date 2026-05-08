package com.baupass.hce

import android.content.Context

object HceTokenStore {
    private const val PREFS = "baupass_hce_prefs"
    private const val KEY_TOKEN = "payload_token"
    private const val KEY_EXPIRES_AT_MS = "expires_at_ms"
    private const val KEY_AID = "aid"

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
}
