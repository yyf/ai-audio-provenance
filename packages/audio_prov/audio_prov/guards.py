from __future__ import annotations

from pathlib import Path

from audio_prov.config import Settings


class GuardError(PermissionError):
    """Raised when a path violates workspace policy."""


def _resolve(path: Path) -> Path:
    return path.resolve(strict=False)


def allowed_roots(settings: Settings) -> list[Path]:
    return [
        _resolve(settings.workspace_path),
        _resolve(settings.fixtures_path),
        _resolve(settings.runs_path),
    ]


def is_allowed(path: Path, settings: Settings) -> bool:
    resolved = _resolve(path)
    for root in allowed_roots(settings):
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def ensure_allowed(path: Path, settings: Settings) -> Path:
    resolved = _resolve(path)
    if not is_allowed(resolved, settings):
        raise GuardError(f"Path not allowed: {path}")
    if resolved.is_symlink():
        target = resolved.resolve()
        if not is_allowed(target, settings):
            raise GuardError(f"Symlink escapes allowlist: {path}")
        return target
    return resolved


def ensure_file_size(path: Path, settings: Settings) -> None:
    size = path.stat().st_size
    if size > settings.max_file_bytes:
        raise GuardError(
            f"File exceeds max size ({size} > {settings.max_file_bytes} bytes): {path}"
        )


def resolve_under_root(relative: str, root: Path, settings: Settings) -> Path:
    candidate = (root / relative).resolve()
    ensure_allowed(candidate, settings)
    return candidate
