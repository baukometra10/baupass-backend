package com.baupass.hce

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyFactory
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.Signature
import java.security.interfaces.ECPrivateKey
import java.security.interfaces.ECPublicKey
import java.security.spec.X509EncodedKeySpec

object DeviceKeyManager {
    private const val ANDROID_KEYSTORE = "AndroidKeyStore"
    private const val KEY_ALIAS = "baupass_hce_device_signing"

    fun getOrCreatePublicKeyDerB64(): String {
        val publicKey = getOrCreateKeyPairPublic()
        return Base64.encodeToString(publicKey.encoded, Base64.NO_WRAP)
    }

    fun signPayloadB64(payload: String): String {
        val privateKey = getPrivateKey()
        val signer = Signature.getInstance("SHA256withECDSA")
        signer.initSign(privateKey)
        signer.update(payload.toByteArray(Charsets.UTF_8))
        val signature = signer.sign()
        return Base64.encodeToString(signature, Base64.NO_WRAP)
    }

    private fun getOrCreateKeyPairPublic(): ECPublicKey {
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        val cert = keyStore.getCertificate(KEY_ALIAS)
        if (cert != null) {
            val pub = cert.publicKey
            val kf = KeyFactory.getInstance(pub.algorithm)
            val spec = X509EncodedKeySpec(pub.encoded)
            return kf.generatePublic(spec) as ECPublicKey
        }

        val kpg = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, ANDROID_KEYSTORE)
        val spec = KeyGenParameterSpec.Builder(
            KEY_ALIAS,
            KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY
        )
            .setAlgorithmParameterSpec(java.security.spec.ECGenParameterSpec("secp256r1"))
            .setDigests(KeyProperties.DIGEST_SHA256)
            .setUserAuthenticationRequired(false)
            .build()
        kpg.initialize(spec)
        val kp = kpg.generateKeyPair()
        return kp.public as ECPublicKey
    }

    private fun getPrivateKey(): ECPrivateKey {
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        val entry = keyStore.getEntry(KEY_ALIAS, null) as? KeyStore.PrivateKeyEntry
        if (entry != null) {
            return entry.privateKey as ECPrivateKey
        }
        // Create if absent.
        getOrCreateKeyPairPublic()
        val created = keyStore.getEntry(KEY_ALIAS, null) as KeyStore.PrivateKeyEntry
        return created.privateKey as ECPrivateKey
    }
}
