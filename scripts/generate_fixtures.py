#!/usr/bin/env python3
"""Generate minimal owned fixtures for CI and docs."""

from __future__ import annotations

import math
import shutil
import struct
import subprocess
import wave
from pathlib import Path

from audio_prov.plugins.verify_demo import sign_demo_manifest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


def write_tone_wav(path: Path, duration: float = 1.0, freq: float = 440.0) -> None:
    sample_rate = 44100
    n_samples = int(sample_rate * duration)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        for i in range(n_samples):
            value = int(32767 * 0.3 * math.sin(2 * math.pi * freq * i / sample_rate))
            wf.writeframes(struct.pack("<h", value))


def maybe_mp3(src_wav: Path, dst_mp3: Path) -> bool:
    if shutil.which("ffmpeg") is None:
        return False
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src_wav), "-c:a", "libmp3lame", "-b:a", "128k", str(dst_mp3)],
        check=True,
        capture_output=True,
    )
    return True


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)

    tone_wav = FIXTURES / "tone.wav"
    write_tone_wav(tone_wav)

    tone_mp3 = FIXTURES / "tone.mp3"
    has_mp3 = maybe_mp3(tone_wav, tone_mp3)

    signed_wav = FIXTURES / "signed-sidecar.wav"
    write_tone_wav(signed_wav, duration=0.5, freq=523.25)
    sign_demo_manifest(
        signed_wav,
        {"synthetic": True, "generator": "fixture-generator", "content_id": "signed-sidecar"},
    )

    broken_wav = FIXTURES / "broken-sig.wav"
    write_tone_wav(broken_wav, duration=0.5, freq=330.0)
    sign_demo_manifest(
        broken_wav,
        {"synthetic": True, "generator": "fixture-generator", "content_id": "broken-sig"},
    )
    sig_path = broken_wav.with_suffix(broken_wav.suffix + ".manifest.sig")
    sig_path.write_text("invalid-signature", encoding="utf-8")

    catalog = {
        "tone-wav": {
            "file": "tone.wav",
            "description": "Structural baseline WAV",
            "format_profile": "pcm_s16le",
        },
        "signed-sidecar": {
            "file": "signed-sidecar.wav",
            "description": "Valid demo sidecar manifest",
            "format_profile": "pcm_s16le",
        },
        "broken-sig": {
            "file": "broken-sig.wav",
            "description": "Invalid demo sidecar signature",
            "format_profile": "pcm_s16le",
        },
        "no-creds-wav": {
            "file": "tone.wav",
            "description": "Typical export without credentials (alias tone-wav)",
            "format_profile": "pcm_s16le",
        },
    }
    if has_mp3:
        catalog["tone-mp3"] = {
            "file": "tone.mp3",
            "description": "Compressed MP3 inspect fixture",
            "format_profile": "mp3_128k",
        }

    (FIXTURES / "catalog.json").write_text(
        __import__("json").dumps(catalog, indent=2),
        encoding="utf-8",
    )
    print(f"Fixtures written to {FIXTURES}")


if __name__ == "__main__":
    main()
