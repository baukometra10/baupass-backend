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

    override fun processCommandApdu(commandApdu: ByteArray?, extras: Bundle?): ByteArray {
        if (commandApdu == null || commandApdu.isEmpty()) {
            return unknownCmdSw
        }

        if (isSelectAid(commandApdu)) {
            return selectOkSw
        }

        if (!HceTokenStore.isTokenValid(this)) {
            return invalidStateSw
        }

        val token = HceTokenStore.getToken(this)
        val tokenBytes = token.toByteArray(Charsets.UTF_8)
        return tokenBytes + selectOkSw
    }

    override fun onDeactivated(reason: Int) {
        // No-op for starter project.
    }

    private fun isSelectAid(apdu: ByteArray): Boolean {
        if (apdu.size < 4) return false
        return apdu[0] == selectAidHeader[0]
            && apdu[1] == selectAidHeader[1]
            && apdu[2] == selectAidHeader[2]
            && apdu[3] == selectAidHeader[3]
    }
}
