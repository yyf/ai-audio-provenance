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


def maybe_mp3_with_cover_art(src_wav: Path, dst_mp3: Path) -> bool:
    """MP3 with embedded MJPEG cover art (common on Suno/Udio exports)."""
    if shutil.which("ffmpeg") is None:
        return False
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src_wav),
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=256x256:d=0.1",
            "-map",
            "0:a",
            "-map",
            "1:v",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "128k",
            "-c:v",
            "mjpeg",
            "-disposition:v",
            "attached_pic",
            "-frames:v",
            "1",
            str(dst_mp3),
        ],
        check=True,
        capture_output=True,
    )
    return True


def maybe_c2pa_signed(src_wav: Path, dst_wav: Path) -> bool:
    from audio_prov.config import Settings
    from audio_prov.plugins.sign_c2pa import sign_c2pa_embed
    from audio_prov.plugins.verify_c2pa import _resolve_tool

    settings = Settings(project_root=ROOT)
    if _resolve_tool(settings.c2patool_path) is None:
        return False
    sign_c2pa_embed(src_wav, settings, output_path=dst_wav)
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
        catalog["no-creds-mp3"] = {
            "file": "tone.mp3",
            "description": "Typical AI export without credentials (MP3)",
            "format_profile": "mp3_128k",
        }
        cover_art_mp3 = FIXTURES / "cover-art.mp3"
        if maybe_mp3_with_cover_art(tone_wav, cover_art_mp3):
            catalog["cover-art-mp3"] = {
                "file": "cover-art.mp3",
                "description": "MP3 with embedded MJPEG cover art (Suno-style)",
                "format_profile": "mp3_128k",
            }

    signed_c2pa_wav = FIXTURES / "signed-c2pa.wav"
    write_tone_wav(signed_c2pa_wav, duration=0.5, freq=440.0)
    if maybe_c2pa_signed(signed_c2pa_wav, signed_c2pa_wav):
        catalog["signed-c2pa"] = {
            "file": "signed-c2pa.wav",
            "description": "Embedded C2PA manifest (c2patool dev cert)",
            "format_profile": "pcm_s16le",
        }

    (FIXTURES / "catalog.json").write_text(
        __import__("json").dumps(catalog, indent=2),
        encoding="utf-8",
    )
    print(f"Fixtures written to {FIXTURES}")


if __name__ == "__main__":
    main()
