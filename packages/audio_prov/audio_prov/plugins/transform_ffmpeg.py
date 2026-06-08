from __future__ import annotations

import subprocess
from pathlib import Path

from audio_prov.config import Settings
from audio_prov.errors import ToolNotFoundError, TransformError
from audio_prov.models import TransformPresetInfo, TransformResult

PRESETS: dict[str, dict] = {
    "aac128": {
        "description": "AAC 128k CBR then decode to WAV",
        "models": "Streaming upload",
        "args": ["-c:a", "aac", "-b:a", "128k"],
        "output_ext": ".wav",
        "decode": True,
    },
    "aac64": {
        "description": "AAC 64k then decode to WAV",
        "models": "Low-bitrate social / preview",
        "args": ["-c:a", "aac", "-b:a", "64k"],
        "output_ext": ".wav",
        "decode": True,
    },
    "mp3_128": {
        "description": "MP3 128k then decode to WAV",
        "models": "Legacy distributor path",
        "args": ["-c:a", "libmp3lame", "-b:a", "128k"],
        "output_ext": ".wav",
        "decode": True,
    },
    "loudnorm_-14": {
        "description": "EBU R128-style loudness normalization then AAC128 decode to WAV",
        "models": "Platform normalization + encode",
        "args": ["-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "128k"],
        "output_ext": ".wav",
        "decode": True,
    },
    "copy": {
        "description": "Remux without re-encode",
        "models": "Control arm",
        "args": ["-c", "copy"],
        "output_ext": None,
        "intermediate_ext": None,
        "decode": False,
    },
}

# Intermediate container must match codec (AAC cannot be written to .mp3).
_INTERMEDIATE_EXT: dict[str, str] = {
    "aac128": ".m4a",
    "aac64": ".m4a",
    "loudnorm_-14": ".m4a",
    "mp3_128": ".mp3",
}


def list_presets() -> list[TransformPresetInfo]:
    return [
        TransformPresetInfo(id=preset_id, description=meta["description"], models=meta["models"])
        for preset_id, meta in PRESETS.items()
    ]


class FfmpegTransformPlugin:
    id = "ffmpeg"
    version = "0.1.0"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def transform(self, path: Path, preset: str, output_dir: Path) -> TransformResult:
        if preset not in PRESETS:
            raise TransformError(
                f"Unknown transform preset: {preset}",
                hint=f"Available: {', '.join(PRESETS)}",
            )

        meta = PRESETS[preset]
        output_dir.mkdir(parents=True, exist_ok=True)
        if preset == "copy":
            intermediate = output_dir / f"{path.stem}_{preset}_intermediate{path.suffix}"
        else:
            ext = _INTERMEDIATE_EXT[preset]
            intermediate = output_dir / f"{path.stem}_{preset}_intermediate{ext}"

        cmd = _ffmpeg_transform_cmd(self.settings, path, preset, meta["args"], intermediate)
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=180)
        except FileNotFoundError as exc:
            raise ToolNotFoundError("ffmpeg", self.settings.ffmpeg_path) from exc
        except subprocess.CalledProcessError as exc:
            raise TransformError(
                f"ffmpeg transform failed: {exc.stderr}",
                hint=_transform_error_hint(exc.stderr or ""),
            ) from exc

        final_path = intermediate
        if meta.get("decode"):
            ext = meta.get("output_ext") or ".wav"
            final_path = output_dir / f"{path.stem}_{preset}{ext}"
            decode_cmd = [
                self.settings.ffmpeg_path,
                "-y",
                "-i",
                str(intermediate),
                str(final_path),
            ]
            subprocess.run(decode_cmd, capture_output=True, text=True, check=True, timeout=180)

        return TransformResult(
            output_path=str(final_path.resolve()),
            preset=preset,
            bytes_out=final_path.stat().st_size,
        )


def _ffmpeg_transform_cmd(
    settings: Settings,
    path: Path,
    preset: str,
    codec_args: list[str],
    output_path: Path,
) -> list[str]:
    """Build ffmpeg command; re-encode presets map first audio stream only."""
    cmd = [settings.ffmpeg_path, "-y", "-i", str(path)]
    if preset != "copy":
        cmd.extend(["-map", "0:a:0"])
    cmd.extend([*codec_args, str(output_path)])
    return cmd


def _transform_error_hint(stderr: str) -> str | None:
    lowered = stderr.lower()
    if "invalid audio stream" in lowered or (
        "video:" in lowered and "mjpeg" in lowered
    ):
        return (
            "Input may include embedded cover art or a non-audio stream. "
            "Re-encode presets use -map 0:a:0; if this persists, check ffprobe -show_streams."
        )
    return None
