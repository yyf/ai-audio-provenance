from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def find_project_root(start: Path | None = None) -> Path:
    if env_root := os.getenv("AUDIO_PROV_ROOT"):
        return Path(env_root).resolve()
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "pyproject.toml").exists() and (candidate / "packages").is_dir():
            return candidate
    return current


@dataclass
class Settings:
    project_root: Path = field(default_factory=find_project_root)
    workspace_dir: str = "workspace"
    fixtures_dir: str = "fixtures"
    runs_dir: str = "runs"
    pipelines_dir: str = "pipelines"
    schemas_dir: str = "schemas"
    max_file_bytes: int = 104_857_600
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    c2patool_path: str = "c2patool"
    c2pa_manifest_path: str | None = None
    c2pa_private_key: str | None = None
    c2pa_sign_cert: str | None = None
    c2pa_ta_url: str | None = None
    c2pa_sign_alg: str = "es256"
    default_transform_preset: str = "aac128"
    verify_plugins: tuple[str, ...] = ("verify.demo", "verify.c2pa")
    detect_plugins: tuple[str, ...] = ("detect.stub", "detect.watermark")

    @property
    def workspace_path(self) -> Path:
        return self.project_root / self.workspace_dir

    @property
    def fixtures_path(self) -> Path:
        return self.project_root / self.fixtures_dir

    @property
    def runs_path(self) -> Path:
        return self.project_root / self.runs_dir

    @property
    def pipelines_path(self) -> Path:
        return self.project_root / self.pipelines_dir

    @property
    def schemas_path(self) -> Path:
        return self.project_root / self.schemas_dir


def get_settings() -> Settings:
    root = find_project_root()
    detect_raw = os.getenv("AUDIO_PROV_DETECT_PLUGINS", "detect.stub,detect.watermark")
    detect_plugins = tuple(p.strip() for p in detect_raw.split(",") if p.strip())
    return Settings(
        project_root=root,
        workspace_dir=os.getenv("AUDIO_PROV_WORKSPACE_DIR", "workspace"),
        fixtures_dir=os.getenv("AUDIO_PROV_FIXTURES_DIR", "fixtures"),
        runs_dir=os.getenv("AUDIO_PROV_RUNS_DIR", "runs"),
        max_file_bytes=int(os.getenv("AUDIO_PROV_MAX_FILE_BYTES", "104857600")),
        ffmpeg_path=os.getenv("AUDIO_PROV_FFMPEG", "ffmpeg"),
        ffprobe_path=os.getenv("AUDIO_PROV_FFPROBE", "ffprobe"),
        c2patool_path=os.getenv("AUDIO_PROV_C2PATOOL", "c2patool"),
        c2pa_manifest_path=os.getenv("AUDIO_PROV_C2PA_MANIFEST") or None,
        c2pa_private_key=os.getenv("AUDIO_PROV_C2PA_PRIVATE_KEY") or None,
        c2pa_sign_cert=os.getenv("AUDIO_PROV_C2PA_SIGN_CERT") or None,
        c2pa_ta_url=os.getenv("AUDIO_PROV_C2PA_TA_URL") or None,
        c2pa_sign_alg=os.getenv("AUDIO_PROV_C2PA_SIGN_ALG", "es256"),
        default_transform_preset=os.getenv("AUDIO_PROV_DEFAULT_PRESET", "aac128"),
        detect_plugins=detect_plugins,
    )
