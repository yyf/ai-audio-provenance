from __future__ import annotations

import json
import subprocess
from pathlib import Path

from audio_prov.config import Settings
from audio_prov.errors import InspectError, ToolNotFoundError
from audio_prov.models import InspectResult
from audio_prov.util import sha256_file


class FfprobeInspectPlugin:
    id = "ffprobe"
    version = "0.1.0"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def inspect(self, path: Path) -> InspectResult:
        cmd = [
            self.settings.ffprobe_path,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60)
        except FileNotFoundError as exc:
            raise ToolNotFoundError("ffprobe", self.settings.ffprobe_path) from exc
        except subprocess.CalledProcessError as exc:
            raise InspectError(f"ffprobe failed: {exc.stderr}") from exc

        data = json.loads(proc.stdout or "{}")
        streams = data.get("streams") or []
        fmt = data.get("format") or {}
        audio = next(
            (s for s in streams if s.get("codec_type") == "audio"),
            streams[0] if streams else {},
        )

        codec = audio.get("codec_name") or fmt.get("format_name")
        bit_rate = _int_or_none(audio.get("bit_rate") or fmt.get("bit_rate"))
        sample_rate = _int_or_none(audio.get("sample_rate"))
        channels = _int_or_none(audio.get("channels"))
        duration = _float_or_none(fmt.get("duration") or audio.get("duration"))
        format_name = fmt.get("format_name")
        format_profile = _format_profile(format_name, codec, bit_rate)

        return InspectResult(
            duration_sec=duration,
            sample_rate=sample_rate,
            channels=channels,
            codec=codec,
            bit_rate=bit_rate,
            format_name=format_name,
            format_profile=format_profile,
            content_hash=sha256_file(path),
        )


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _format_profile(format_name: str | None, codec: str | None, bit_rate: int | None) -> str:
    base = codec or format_name or "unknown"
    if bit_rate:
        kbps = round(bit_rate / 1000)
        return f"{base}_{kbps}k"
    return base
