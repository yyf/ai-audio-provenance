from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from audio_prov.config import Settings


@dataclass
class ProvenanceError(Exception):
    code: str
    message: str
    hint: str | None = None

    def __str__(self) -> str:
        if self.hint:
            return f"{self.code}: {self.message} ({self.hint})"
        return f"{self.code}: {self.message}"

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"error": self.code, "message": self.message}
        if self.hint:
            payload["hint"] = self.hint
        return payload


class AssetNotFoundError(ProvenanceError):
    def __init__(self, ref: str) -> None:
        super().__init__(
            code="asset_not_found",
            message=f"Unknown asset: {ref}",
            hint="Register with register_workspace_file or pass a workspace filename.",
        )


class PipelineNotFoundError(ProvenanceError):
    def __init__(self, pipeline_id: str, available: list[str] | None = None) -> None:
        hint = f"Valid ids: {', '.join(available)}" if available else None
        super().__init__(
            code="pipeline_not_found",
            message=f"Pipeline not found: {pipeline_id}",
            hint=hint,
        )


class ToolNotFoundError(ProvenanceError):
    def __init__(self, tool: str, path: str) -> None:
        super().__init__(
            code="tool_not_found",
            message=f"{tool} not found at '{path}'",
            hint="Install ffmpeg (ffprobe/ffmpeg) or set AUDIO_PROV_FFMPEG / AUDIO_PROV_FFPROBE.",
        )


class TransformError(ProvenanceError):
    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(code="transform_failed", message=message, hint=hint)


class InspectError(ProvenanceError):
    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(code="inspect_failed", message=message, hint=hint)


def check_setup(settings: Settings) -> dict[str, Any]:
    """Return prerequisite status for ffmpeg/ffprobe (optional c2patool)."""
    import shutil
    from pathlib import Path

    checks: list[dict[str, Any]] = []

    for name, path_str, required in (
        ("ffprobe", settings.ffprobe_path, True),
        ("ffmpeg", settings.ffmpeg_path, True),
        ("c2patool", settings.c2patool_path, False),
    ):
        path = Path(path_str)
        on_path = shutil.which(path_str) is not None
        exists = path.is_file() or on_path
        resolved = str(path.resolve()) if path.is_file() else path_str
        checks.append(
            {
                "tool": name,
                "required": required,
                "ok": exists,
                "configured_path": path_str,
                "resolved": resolved if exists else None,
            }
        )

    required_ok = all(c["ok"] for c in checks if c["required"])
    return {
        "ready": required_ok,
        "checks": checks,
        "workspace": str(settings.workspace_path),
        "project_root": str(settings.project_root),
    }
