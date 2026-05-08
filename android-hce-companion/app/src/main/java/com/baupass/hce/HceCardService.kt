package com.baupass.hce

import android.nfc.cardemulation.HostApduService
import android.os.Bundle

class HceCardService : HostApduService() {

    private val selectAidHeader = byteArrayOf(
        0x00.toByte(),
        0xA4.toByte(),
        0x04.toByte(),
        0x00.toByte()
    )

    private val selectOkSw = byteArrayOf(0x90.toByte(), 0x00.toByte())
    private val invalidStateSw = byteArrayOf(0x69.toByte(), 0x85.toByte())
    private val unknownCmdSw = byteArrayOf(0x6A.toByte(), 0x82.toByte())
    private val wrongP1P2Sw = byteArrayOf(0x6B.toByte(), 0x00.toByte())
    private val maxChunkBytes = 220
    private var aidSelected = false

    override fun processCommandApdu(commandApdu: ByteArray?, extras: Bundle?): ByteArray {
        if (commandApdu == null || commandApdu.isEmpty()) {
            return unknownCmdSw
        }

        if (isSelectAid(commandApdu)) {
            aidSelected = true
            return selectOkSw
        }

        if (!aidSelected) {
            return invalidStateSw
        }

        if (!HceTokenStore.isTokenValid(this)) {
            return invalidStateSw
        }

        val token = HceTokenStore.getToken(this)
        val tokenBytes = token.toByteArray(Charsets.UTF_8)
        return when (commandApdu.getOrNull(1)?.toInt()?.and(0xFF)) {
            0xCA -> buildChunkResponse(tokenBytes, 0, maxChunkBytes) // GET DATA
            0xB0 -> {
                if (commandApdu.size < 5) {
                    wrongP1P2Sw
                } else {
                    val p1 = commandApdu[2].toInt() and 0xFF
                    val p2 = commandApdu[3].toInt() and 0xFF
                    val offset = (p1 shl 8) or p2
                    val le = commandApdu[4].toInt() and 0xFF
                    val wanted = if (le == 0) maxChunkBytes else minOf(le, maxChunkBytes)
                    buildChunkResponse(tokenBytes, offset, wanted)
                }
            }
            else -> {
                // Backward-compat for very simple readers: first token chunk.
                buildChunkResponse(tokenBytes, 0, maxChunkBytes)
            }
        }
    }

    override fun onDeactivated(reason: Int) {
        aidSelected = false
    }

    private fun isSelectAid(apdu: ByteArray): Boolean {
        if (apdu.size < 4) return false
        return apdu[0] == selectAidHeader[0]
            && apdu[1] == selectAidHeader[1]
            && apdu[2] == selectAidHeader[2]
            && apdu[3] == selectAidHeader[3]
    }

    private fun buildChunkResponse(data: ByteArray, offset: Int, requestedLength: Int): ByteArray {
        if (offset < 0 || offset > data.size) return wrongP1P2Sw
        val safeLength = requestedLength.coerceAtLeast(1)
        val end = minOf(data.size, offset + safeLength)
        val chunk = data.copyOfRange(offset, end)
        val remaining = data.size - end
        val sw = if (remaining > 0) {
            byteArrayOf(0x61.toByte(), minOf(remaining, 255).toByte())
        } else {
            selectOkSw
        }
        return chunk + sw
    }
}
