from __future__ import annotations

import json
import subprocess
from pathlib import Path

from audio_prov.config import Settings
from audio_prov.models import TagResult


class FfprobeMetadataPlugin:
    id = "tags"
    version = "0.1.0"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def extract(self, path: Path) -> TagResult:
        cmd = [
            self.settings.ffprobe_path,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            str(path),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
        except (FileNotFoundError, subprocess.CalledProcessError):
            return TagResult()

        data = json.loads(proc.stdout or "{}")
        tags = data.get("format", {}).get("tags") or {}
        normalized = {str(k).lower(): str(v) for k, v in tags.items()}
        return TagResult(tags=normalized)
