#!/usr/bin/env python3
"""Merge audio-provenance MCP into Claude Desktop config (macOS)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CLAUDE_CONFIG = Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"


def _find_binary(name: str) -> str | None:
    for prefix in ("/opt/homebrew/bin", "/usr/local/bin"):
        path = Path(prefix) / name
        if path.is_file():
            return str(path)
    return None


def build_audio_server(repo: Path) -> dict:
    mcp_bin = repo / ".venv" / "bin" / "audio-prov-mcp"
    if not mcp_bin.is_file():
        raise FileNotFoundError(
            f"MCP entrypoint not found: {mcp_bin}\n"
            "Create the venv and install packages first (see docs/mcp-setup.md)."
        )

    env: dict[str, str] = {
        "AUDIO_PROV_ROOT": str(repo),
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
    }
    ffmpeg = _find_binary("ffmpeg")
    ffprobe = _find_binary("ffprobe")
    if ffmpeg:
        env["AUDIO_PROV_FFMPEG"] = ffmpeg
    if ffprobe:
        env["AUDIO_PROV_FFPROBE"] = ffprobe

    return {
        "command": str(mcp_bin),
        "args": [],
        "env": env,
    }


def main() -> int:
    try:
        audio_server = build_audio_server(REPO)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1

    if CLAUDE_CONFIG.exists():
        config = json.loads(CLAUDE_CONFIG.read_text(encoding="utf-8"))
    else:
        CLAUDE_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        config = {"mcpServers": {}}

    config.setdefault("mcpServers", {})
    config["mcpServers"]["audio-provenance"] = audio_server

    CLAUDE_CONFIG.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {CLAUDE_CONFIG}")
    print("Restart Claude Desktop, then copy AI audio into workspace/ and use analyze_ai_audio.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
