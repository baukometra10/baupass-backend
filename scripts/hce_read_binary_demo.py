"""Minimal READ BINARY loop demo for WorkPass HCE APDU v2.

This script demonstrates how a reader can fetch a token from the Android HCE card
using SELECT AID + READ BINARY chunking until SW=9000.

Replace `transmit_apdu(...)` with your reader SDK call.
"""

from __future__ import annotations

AID = bytes.fromhex("F0010203040506")


def build_select_aid(aid: bytes) -> bytes:
    return bytes([0x00, 0xA4, 0x04, 0x00, len(aid)]) + aid


def build_read_binary(offset: int, le: int = 220) -> bytes:
    p1 = (offset >> 8) & 0xFF
    p2 = offset & 0xFF
    return bytes([0x00, 0xB0, p1, p2, le & 0xFF])


def parse_sw(response: bytes) -> tuple[bytes, int, int]:
    if len(response) < 2:
        raise ValueError("APDU response too short")
    data = response[:-2]
    sw1 = response[-2]
    sw2 = response[-1]
    return data, sw1, sw2


def read_full_token(transmit_apdu):
    # 1) SELECT AID
    sel_resp = transmit_apdu(build_select_aid(AID))
    _, sw1, sw2 = parse_sw(sel_resp)
    if (sw1, sw2) != (0x90, 0x00):
        raise RuntimeError(f"SELECT failed: {sw1:02X}{sw2:02X}")

    # 2) READ BINARY in chunks
    offset = 0
    chunks = []
    while True:
        resp = transmit_apdu(build_read_binary(offset, 220))
        data, sw1, sw2 = parse_sw(resp)
        chunks.append(data)
        offset += len(data)

        if sw1 == 0x90 and sw2 == 0x00:
            break
        if sw1 == 0x61:
            # More data available; keep reading next offset.
            continue
        raise RuntimeError(f"READ failed at offset {offset}: {sw1:02X}{sw2:02X}")

    token = b"".join(chunks).decode("utf-8", errors="replace")
    return token


if __name__ == "__main__":
    def _dummy_transmit(_apdu: bytes) -> bytes:
        raise NotImplementedError("Wire this to your reader SDK transmit call")

    print("Use read_full_token(transmit_apdu) with your reader transport.")
