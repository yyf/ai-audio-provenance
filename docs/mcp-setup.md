# MCP Setup — Audio Provenance

## Prerequisites

- Python 3.11+
- [ffmpeg](https://ffmpeg.org/) (`ffmpeg` and `ffprobe` on PATH)
- Optional: [c2patool](https://opensource.contentauthenticity.org/docs/c2patool/) for C2PA verify on real exports

## Install

```bash
cd ai-audio-provenance
python3 -m venv .venv
source .venv/bin/activate
pip install -e packages/audio_prov -e packages/audio_prov_mcp
python scripts/generate_fixtures.py
```

## Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "audio-provenance": {
      "command": "/ABS/PATH/ai-audio-provenance/.venv/bin/audio-prov-mcp",
      "env": {
        "AUDIO_PROV_ROOT": "/ABS/PATH/ai-audio-provenance"
      }
    }
  }
}
```

Restart Claude Desktop after saving.

## Analyze real-world AI audio

1. Copy your file (MP3/M4A/WAV) into `workspace/`
2. In Claude, try:

> Use `list_workspace_files`, then `register_workspace_file` for my file, then run the `analyze-ai-audio` prompt.

For distribution stress:

> Run the `real-world-stress-test` prompt with preset `aac128`.

## CLI (without MCP)

```bash
audio-prov run provenance-analysis@1 --asset tone-wav --json
audio-prov verify --asset signed-sidecar --json
```

## Fixtures

Committed fixtures in `fixtures/` support CI. Register by fixture id (e.g. `tone-wav`, `signed-sidecar`).

## Environment

| Variable | Default | Description |
|----------|---------|-------------|
| `AUDIO_PROV_ROOT` | auto-detect | Project root |
| `AUDIO_PROV_WORKSPACE_DIR` | `workspace` | User audio directory |
| `AUDIO_PROV_FFMPEG` | `ffmpeg` | ffmpeg binary |
| `AUDIO_PROV_FFPROBE` | `ffprobe` | ffprobe binary |
| `AUDIO_PROV_C2PATOOL` | `c2patool` | C2PA tool binary |

## Disclaimer

Analysis reports technical evidence only. Absent credentials do **not** prove an file is AI-generated. Demo sidecar manifests use development keys only.
