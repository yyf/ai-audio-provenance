# ai-audio-provenance

Open-source **audio provenance** infrastructure with an MCP adapter so AI assistants can run auditable provenance analysis on **real-world AI audio** (local workspace files): inspect → verify credentials → distribution-stress → report.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e packages/audio_prov -e packages/audio_prov_mcp
python scripts/generate_fixtures.py
audio-prov run provenance-analysis@1 --asset tone-wav
```

See [docs/mcp-setup.md](docs/mcp-setup.md) for Claude Desktop configuration.

```bash
python scripts/wire_claude_desktop.py   # macOS: merge MCP config, then restart Claude
cp ~/Downloads/your-ai-track.mp3 workspace/
```

In Claude: use MCP `list_workspace_files` → `register_workspace_file` → tool **`analyze_ai_audio`** (not `provenance_run` with prompt name).

## Features

- **Workspace-first:** analyze your own MP3/M4A/WAV exports in `workspace/`
- **Multi-signal reports:** structural, verified, simulated (and inferred later)
- **MCP tools:** `register_workspace_file`, `provenance_run`, `verify_provenance`, etc.
- **Distribution presets:** `aac128`, `aac64`, `mp3_128`, `loudnorm_-14`, `copy`
- **Pluggable verify:** demo sidecar manifests + optional C2PA via `c2patool`

## Disclaimer

Analysis reports technical evidence only. Absent credentials do not prove synthetic origin. Demo sidecar manifests use development keys only.

## License

MIT
