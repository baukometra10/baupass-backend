"""Generate WhatsApp-style call tones (original motifs, not copyrighted WA audio)."""
from __future__ import annotations

import math
import os
import struct
import wave

SR = 44100
SOUNDS = os.path.dirname(os.path.abspath(__file__))


def synth(freq: float, dur: float, *, vol: float = 0.28, kind: str = "sine", fade_in: float = 0.01, fade_out: float = 0.04):
    n = int(SR * dur)
    out = []
    for i in range(n):
        t = i / SR
        env = 1.0
        if fade_in > 0:
            env *= min(1.0, t / fade_in)
        if fade_out > 0:
            rem = dur - t
            env *= min(1.0, rem / fade_out)
        if kind == "soft":
            s = math.sin(2 * math.pi * freq * t)
            s += 0.35 * math.sin(2 * math.pi * freq * 2 * t)
            s += 0.12 * math.sin(2 * math.pi * freq * 3 * t)
            s *= 0.72
        else:
            s = math.sin(2 * math.pi * freq * t)
        out.append(s * vol * env)
    return out


def mix(*tracks):
    length = max(len(t) for t in tracks)
    out = [0.0] * length
    for tr in tracks:
        for i, v in enumerate(tr):
            out[i] += v
    peak = max(1e-9, max(abs(x) for x in out))
    if peak > 0.95:
        out = [x * (0.95 / peak) for x in out]
    return out


def silence(dur: float):
    return [0.0] * int(SR * dur)


def write_wav(path: str, samples):
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        frames = b"".join(
            struct.pack("<h", max(-32767, min(32767, int(x * 32767)))) for x in samples
        )
        w.writeframes(frames)


def build_incoming():
    """Melodic messenger-style ringtone (incoming) — not a PSTN dual-tone."""
    seq = [
        (523.25, 0.11, "soft"),
        (783.99, 0.11, "soft"),
        (1046.5, 0.16, "soft"),
        (0.0, 0.07, "sine"),
        (659.25, 0.10, "soft"),
        (783.99, 0.10, "soft"),
        (1046.5, 0.20, "soft"),
    ]
    motif = []
    for hz, dur, kind in seq:
        if hz <= 0:
            motif += silence(dur)
        else:
            motif += synth(hz, dur, vol=0.34, kind=kind, fade_in=0.008, fade_out=0.03)

    echo = silence(0.04)
    for hz, dur, kind in seq:
        if hz <= 0:
            echo += silence(dur)
        else:
            echo += synth(hz * 1.01, dur, vol=0.15, kind=kind, fade_in=0.008, fade_out=0.03)

    body_len = len(motif) + int(0.05 * SR)
    incoming = mix(motif + silence(0.05), echo[:body_len])
    incoming += silence(1.55)
    return incoming


def dual_pulse(dur: float = 0.40, vol: float = 0.22):
    a = synth(440.0, dur, vol=vol, kind="sine", fade_in=0.015, fade_out=0.05)
    b = synth(480.0, dur, vol=vol, kind="sine", fade_in=0.015, fade_out=0.05)
    return mix(a, b)


def build_outgoing():
    """Classic phone ringback (outgoing) — what WhatsApp callers hear."""
    return dual_pulse() + silence(0.20) + dual_pulse() + silence(4.0)


def main():
    incoming = build_incoming()
    outgoing = build_outgoing()
    in_wav = os.path.join(SOUNDS, "_incoming_wa.wav")
    out_wav = os.path.join(SOUNDS, "_outgoing_wa.wav")
    write_wav(in_wav, incoming)
    write_wav(out_wav, outgoing)
    print(f"incoming_sec={len(incoming)/SR:.3f}")
    print(f"outgoing_sec={len(outgoing)/SR:.3f}")
    print(in_wav)
    print(out_wav)


if __name__ == "__main__":
    main()
