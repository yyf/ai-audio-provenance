from __future__ import annotations

from typing import Any

from audio_prov.assets import AssetStore
from audio_prov.pipeline import PipelineRunner


def batch_analyze_workspace(
    store: AssetStore,
    runner: PipelineRunner,
    pipeline_id: str = "provenance-analysis@1",
    preset: str | None = None,
    glob_pattern: str | None = None,
) -> dict[str, Any]:
    """Register (if needed) and analyze every audio file in workspace/."""
    files = store.list_workspace_files(glob_pattern)
    if not files:
        return {"count": 0, "results": [], "pipeline_id": pipeline_id}

    options = {"preset": preset} if preset else {}
    results: list[dict[str, Any]] = []

    for entry in files:
        name = entry["name"]
        asset = store.resolve_asset_ref(name)
        audit, summary = runner.run(pipeline_id, asset.asset_id, options=options)
        results.append(
            {
                "filename": name,
                "asset_id": asset.asset_id,
                "summary": summary,
                "run_id": audit.run_id,
            }
        )

    return {
        "count": len(results),
        "pipeline_id": pipeline_id,
        "results": results,
    }
