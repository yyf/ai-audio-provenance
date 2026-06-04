from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def slug_from_filename(name: str) -> str:
    stem = Path(name).stem
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in stem.lower())
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "asset"
