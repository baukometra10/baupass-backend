package com.baupass.hce

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters

class BootstrapWorker(
    context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {

    private val apiClient = ApiClient()

    override suspend fun doWork(): Result {
        if (!HceTokenStore.hasBootstrapConfig(applicationContext)) {
            return Result.success()
        }

        return try {
            val baseUrl = HceTokenStore.getBaseUrl(applicationContext)
            val workerToken = HceTokenStore.getWorkerToken(applicationContext)
            val deviceId = HceTokenStore.getDeviceId(applicationContext)
            apiClient.registerHceDevice(baseUrl, workerToken, deviceId)
            val result = apiClient.fetchHceBootstrap(baseUrl, workerToken, deviceId)
            val expiresAtMs = System.currentTimeMillis() + (result.remainingSec.coerceAtLeast(20) * 1000L)
            HceTokenStore.save(applicationContext, result.payloadToken, expiresAtMs, result.aid)
            Result.success()
        } catch (_: Exception) {
            Result.retry()
        }
    }
}
