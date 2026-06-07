# Workspace — real AI-generated audio

Drop files here for Claude Desktop testing:

```bash
cp ~/Downloads/suno-export.mp3 workspace/
```

Supported: `.wav`, `.mp3`, `.m4a`, `.aac`, `.flac`, `.ogg`

## Claude test prompts

After restarting Claude Desktop (MCP wired via `python scripts/wire_claude_desktop.py`):

**1. List and analyze**

> Use audio-provenance MCP: `list_workspace_files`, `register_workspace_file` for `my-track.mp3`, then call the **`analyze_ai_audio`** tool with the returned asset_id. Summarize the report in a table.

**2. Distribution stress**

> Call **`real_world_stress_test`** on the same asset_id with preset `aac128`.

**3. Optional user hints (declared generator — not verified)**

> Register `my-track.mp3` with user_hints_json `{"generator": "Suno", "synthetic": true}` then run **`analyze_ai_audio`**.

**4. Batch (all files in workspace)**

> Sync: **`analyze_workspace`** or CLI `audio-prov batch --json`  
> Large catalogs: **`analyze_workspace_async`** → poll **`get_batch_run(batch_id)`**

**5. Demo credentials**

> Sidecar: `sign_demo_sidecar` → re-run **`analyze_ai_audio`** — Verified: `valid`  
> C2PA: `sign_c2pa_manifest` → re-run **`analyze_ai_audio`** — Verified: `valid` (dev cert)

Only analyze files you have the right to use.
