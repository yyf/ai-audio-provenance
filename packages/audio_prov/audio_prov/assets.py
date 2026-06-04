from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from audio_prov.config import Settings, get_settings
from audio_prov.guards import ensure_allowed, ensure_file_size, resolve_under_root
from audio_prov.models import Asset, OriginContext
from audio_prov.util import sha256_file, slug_from_filename

AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}


@dataclass
class AssetStore:
    settings: Settings = field(default_factory=get_settings)
    _workspace: dict[str, Asset] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._load_registry()

    def _registry_path(self) -> Path:
        registry_dir = self.settings.project_root / ".audio_prov"
        registry_dir.mkdir(parents=True, exist_ok=True)
        return registry_dir / "workspace_registry.json"

    def _load_registry(self) -> None:
        path = self._registry_path()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        for item in data.get("assets", []):
            asset = Asset.model_validate(item)
            if Path(asset.path).is_file():
                self._workspace[asset.asset_id] = asset

    def _save_registry(self) -> None:
        payload = {"assets": [a.model_dump() for a in self._workspace.values()]}
        self._registry_path().write_text(
            json.dumps(payload, indent=2, default=str),
            encoding="utf-8",
        )

    def _fixtures_catalog_path(self) -> Path:
        return self.settings.fixtures_path / "catalog.json"

    def load_fixtures_catalog(self) -> dict[str, dict]:
        path = self._fixtures_catalog_path()
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def list_workspace_files(self, glob_pattern: str | None = None) -> list[dict]:
        root = self.settings.workspace_path
        root.mkdir(parents=True, exist_ok=True)
        paths = sorted(root.iterdir()) if not glob_pattern else sorted(root.glob(glob_pattern))
        files = []
        for path in paths:
            if not path.is_file():
                continue
            if path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            stat = path.stat()
            files.append(
                {
                    "name": path.name,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                }
            )
        return files

    def register_workspace_file(
        self,
        filename: str,
        user_hints: dict | None = None,
    ) -> Asset:
        path = resolve_under_root(filename, self.settings.workspace_path, self.settings)
        if not path.is_file():
            raise FileNotFoundError(f"Workspace file not found: {filename}")
        ensure_file_size(path, self.settings)
        content_hash = sha256_file(path)
        asset_id = slug_from_filename(path.name)
        if asset_id in self._workspace and self._workspace[asset_id].content_hash != content_hash:
            asset_id = f"{asset_id}-{content_hash[:8]}"
        asset = Asset(
            asset_id=asset_id,
            path=str(path),
            content_hash=content_hash,
            origin_context=OriginContext.USER_PROVIDED,
            user_hints=user_hints or {},
        )
        self._workspace[asset_id] = asset
        self._save_registry()
        return asset

    def resolve_asset_ref(self, ref: str, auto_register: bool = True) -> Asset:
        """Resolve asset_id, workspace filename, path, or content hash."""
        ref = ref.strip()
        if ref in self._workspace:
            return self._workspace[ref]

        # content hash lookup
        if len(ref) >= 32 and all(c in "0123456789abcdef" for c in ref.lower()):
            for asset in self._workspace.values():
                if asset.content_hash == ref or asset.content_hash.startswith(ref):
                    return asset

        # filename or path under workspace
        candidate_name = Path(ref).name
        if auto_register:
            ws = self.settings.workspace_path
            for name in {ref, candidate_name}:
                path = ws / name
                if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS:
                    return self.register_workspace_file(name)

        # by asset_id slug from filename
        slug = slug_from_filename(candidate_name)
        if slug in self._workspace:
            return self._workspace[slug]

        for asset in self._workspace.values():
            if Path(asset.path).name.lower() == candidate_name.lower():
                return asset

        return self.get_asset(ref)

    def get_fixture_asset(self, fixture_id: str) -> Asset:
        catalog = self.load_fixtures_catalog()
        if fixture_id not in catalog:
            raise KeyError(f"Unknown fixture: {fixture_id}")
        entry = catalog[fixture_id]
        rel = entry["file"]
        path = resolve_under_root(rel, self.settings.fixtures_path, self.settings)
        if not path.is_file():
            raise FileNotFoundError(f"Fixture file missing: {path}")
        ensure_file_size(path, self.settings)
        return Asset(
            asset_id=fixture_id,
            path=str(path),
            content_hash=sha256_file(path),
            origin_context=OriginContext.FIXTURE,
            format_profile=entry.get("format_profile"),
            user_hints=entry.get("user_hints", {}),
        )

    def list_fixtures(self) -> list[dict]:
        catalog = self.load_fixtures_catalog()
        return [
            {
                "asset_id": fixture_id,
                "file": entry["file"],
                "description": entry.get("description", ""),
                "format_profile": entry.get("format_profile"),
            }
            for fixture_id, entry in catalog.items()
        ]

    def get_asset(self, asset_id: str) -> Asset:
        if asset_id in self._workspace:
            return self._workspace[asset_id]
        try:
            return self.get_fixture_asset(asset_id)
        except KeyError:
            pass
        raise KeyError(
            f"Unknown asset: {asset_id}. "
            "Call register_workspace_file first or pass the workspace filename "
            "(e.g. WOT_s.wav) to auto-register."
        )

    def resolve_path(self, asset: Asset) -> Path:
        path = ensure_allowed(Path(asset.path), self.settings)
        if not path.is_file():
            raise FileNotFoundError(f"Asset file missing: {path}")
        ensure_file_size(path, self.settings)
        return path
