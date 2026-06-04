#!/usr/bin/env python3
"""Merge audio-provenance MCP into Claude Desktop config (macOS)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CLAUDE_CONFIG = Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
SNIPPET = REPO / "examples/claude_desktop_config.json"


def main() -> int:
    if not SNIPPET.exists():
        print(f"Missing snippet: {SNIPPET}", file=sys.stderr)
        return 1

    snippet = json.loads(SNIPPET.read_text(encoding="utf-8"))
    audio_server = snippet["mcpServers"]["audio-provenance"]

    if CLAUDE_CONFIG.exists():
        config = json.loads(CLAUDE_CONFIG.read_text(encoding="utf-8"))
    else:
        CLAUDE_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        config = {"mcpServers": {}}

    config.setdefault("mcpServers", {})
    config["mcpServers"]["audio-provenance"] = audio_server

    CLAUDE_CONFIG.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {CLAUDE_CONFIG}")
    print("Restart Claude Desktop, then copy AI audio into workspace/ and use analyze-ai-audio.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
