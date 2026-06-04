from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from audio_prov.config import Settings
from audio_prov.models import VerifyResult, VerifyStatus


class C2paVerifyPlugin:
    id = "c2pa"
    version = "0.1.0"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def verify(self, path: Path) -> VerifyResult:
        tool = self.settings.c2patool_path
        if shutil.which(tool) is None:
            return VerifyResult(
                plugin_id="verify.c2pa",
                plugin_version=self.version,
                status=VerifyStatus.ABSENT,
                details={
                    "reason": "c2patool_not_installed",
                    "hint": f"Install c2patool or set path: {tool}",
                },
            )

        try:
            proc = subprocess.run(
                [tool, str(path)],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            return VerifyResult(
                plugin_id="verify.c2pa",
                plugin_version=self.version,
                status=VerifyStatus.INVALID,
                details={"reason": "c2patool_timeout"},
            )

        output = (proc.stdout or "") + (proc.stderr or "")
        lowered = output.lower()

        no_manifest_phrases = (
            "no manifest" in lowered
            or "no c2pa" in lowered
            or "manifest store not found" in lowered
        )
        if no_manifest_phrases:
            return VerifyResult(
                plugin_id="verify.c2pa",
                plugin_version=self.version,
                status=VerifyStatus.ABSENT,
                details={"reason": "no_embedded_c2pa_manifest"},
            )

        if proc.returncode != 0 or "validation status" in lowered and "invalid" in lowered:
            return VerifyResult(
                plugin_id="verify.c2pa",
                plugin_version=self.version,
                status=VerifyStatus.INVALID,
                details={"reason": "c2pa_validation_failed", "output_excerpt": output[:2000]},
            )

        if "valid" in lowered or proc.returncode == 0:
            return VerifyResult(
                plugin_id="verify.c2pa",
                plugin_version=self.version,
                status=VerifyStatus.VALID,
                details={"reason": "c2pa_validation_ok", "output_excerpt": output[:2000]},
            )

        return VerifyResult(
            plugin_id="verify.c2pa",
            plugin_version=self.version,
            status=VerifyStatus.ABSENT,
            details={"reason": "c2pa_indeterminate", "output_excerpt": output[:2000]},
        )
