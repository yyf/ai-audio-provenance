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

### One-time wiring (macOS)

From the repo root (merges into your existing `claude_desktop_config.json`):

```bash
python scripts/wire_claude_desktop.py
```

Or paste manually from [examples/claude_desktop_config.json](../examples/claude_desktop_config.json).

**Restart Claude Desktop** after saving. Confirm **audio-provenance** appears under MCP tools (hammer icon).

The config sets `AUDIO_PROV_ROOT` and full paths to Homebrew `ffmpeg` / `ffprobe` so Claude’s sandboxed MCP process can analyze audio.

### Test with real AI-generated audio

1. Export or download your file (Suno, Udio, TTS, etc.) — **MP3/M4A/WAV**.
2. Copy into `workspace/`:

   ```bash
   cp ~/Downloads/my-ai-track.mp3 workspace/
   ```

3. In Claude, send:

   > Use audio-provenance MCP: `list_workspace_files`, `register_workspace_file` for `my-ai-track.mp3`, then call **`analyze_ai_audio`** with that asset_id. Summarize structural and verified blocks.

4. For transcode survival:

   > Call **`real_world_stress_test`** on the same asset_id with preset `aac128`.

5. Read outputs on disk (optional):

   ```bash
   ls -lt runs/*/summary.md | head -1
   ```

Reports land in `runs/<uuid>/` (`report.json`, `summary.md`, `run.json`).

### Troubleshooting

| Issue | Fix |
|-------|-----|
| MCP server not listed | Restart Claude; check `~/Library/Logs/Claude/mcp*.log` |
| ffprobe not found | Re-run `wire_claude_desktop.py` (sets Homebrew paths) |
| Path not allowed | File must be under `workspace/` |
| verify always absent | Normal for most exports; install `c2patool` for C2PA |

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
