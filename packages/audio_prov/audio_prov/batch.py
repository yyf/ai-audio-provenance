from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime
from typing import Any

from audio_prov.assets import AssetStore
from audio_prov.audit import finalize_batch, init_batch_state, load_batch, save_batch_state
from audio_prov.config import Settings
from audio_prov.pipeline import PipelineRunner

_active_batches: dict[str, threading.Thread] = {}


def batch_analyze_workspace(
    store: AssetStore,
    runner: PipelineRunner,
    pipeline_id: str = "provenance-analysis@1",
    preset: str | None = None,
    glob_pattern: str | None = None,
) -> dict[str, Any]:
    """Register (if needed) and analyze every audio file in workspace/ (blocking)."""
    batch_id = str(uuid.uuid4())
    files = store.list_workspace_files(glob_pattern)
    init_batch_state(
        runner.settings,
        batch_id=batch_id,
        pipeline_id=pipeline_id,
        preset=preset,
        total=len(files),
    )
    payload = _execute_batch(
        store,
        runner,
        batch_id=batch_id,
        pipeline_id=pipeline_id,
        preset=preset,
        files=files,
    )
    return format_batch_status(payload, runner.settings)


def start_batch_job(
    store: AssetStore,
    runner: PipelineRunner,
    pipeline_id: str = "provenance-analysis@1",
    preset: str | None = None,
    glob_pattern: str | None = None,
) -> dict[str, Any]:
    """Start a background batch job; poll with load_batch / get_batch_run."""
    batch_id = str(uuid.uuid4())
    files = store.list_workspace_files(glob_pattern)
    init_batch_state(
        runner.settings,
        batch_id=batch_id,
        pipeline_id=pipeline_id,
        preset=preset,
        total=len(files),
        async_mode=True,
    )

    if not files:
        payload = _execute_batch(
            store,
            runner,
            batch_id=batch_id,
            pipeline_id=pipeline_id,
            preset=preset,
            files=[],
        )
        return format_batch_status(payload, runner.settings, async_started=False)

    thread = threading.Thread(
        target=_run_batch_thread,
        args=(store, runner, batch_id, pipeline_id, preset, files),
        name=f"batch-{batch_id[:8]}",
        daemon=True,
    )
    _active_batches[batch_id] = thread
    thread.start()

    payload = load_batch(runner.settings, batch_id)
    response = format_batch_status(payload, runner.settings, async_started=True)
    response["poll_hint"] = "Call get_batch_run(batch_id) until status is completed or failed."
    return response


def cancel_batch_job(settings: Settings, batch_id: str) -> dict[str, Any]:
    """Request cancellation of a running async batch."""
    payload = load_batch(settings, batch_id)
    if payload["status"] in {"completed", "failed", "cancelled"}:
        return {"batch_id": batch_id, "status": payload["status"], "cancelled": False}

    batch_dir = settings.runs_path / f"batch-{batch_id}"
    batch_dir.mkdir(parents=True, exist_ok=True)
    (batch_dir / "cancel.flag").write_text("1", encoding="utf-8")
    payload["status"] = "cancelling"
    save_batch_state(settings, payload)
    return {"batch_id": batch_id, "status": "cancelling", "cancelled": True}


def _run_batch_thread(
    store: AssetStore,
    runner: PipelineRunner,
    batch_id: str,
    pipeline_id: str,
    preset: str | None,
    files: list[dict],
) -> None:
    try:
        _execute_batch(
            store,
            runner,
            batch_id=batch_id,
            pipeline_id=pipeline_id,
            preset=preset,
            files=files,
        )
    finally:
        _active_batches.pop(batch_id, None)


def _execute_batch(
    store: AssetStore,
    runner: PipelineRunner,
    *,
    batch_id: str,
    pipeline_id: str,
    preset: str | None,
    files: list[dict],
) -> dict[str, Any]:
    settings = runner.settings
    batch_dir = settings.runs_path / f"batch-{batch_id}"
    cancel_flag = batch_dir / "cancel.flag"
    options = {"preset": preset} if preset else {}
    results: list[dict[str, Any]] = []

    payload = load_batch(settings, batch_id)
    payload["status"] = "running"
    save_batch_state(settings, payload)

    try:
        for index, entry in enumerate(files, start=1):
            if cancel_flag.is_file():
                payload = load_batch(settings, batch_id)
                payload["status"] = "cancelled"
                payload["completed"] = len(results)
                payload["count"] = len(results)
                payload["results"] = results
                payload["finished_at"] = datetime.now(tz=UTC).isoformat()
                finalize_batch(settings, payload)
                return payload

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

            payload = load_batch(settings, batch_id)
            payload["completed"] = index
            payload["count"] = len(results)
            payload["results"] = results
            save_batch_state(settings, payload)

        payload = load_batch(settings, batch_id)
        payload["status"] = "completed"
        payload["completed"] = len(results)
        payload["count"] = len(results)
        payload["results"] = results
        payload["finished_at"] = datetime.now(tz=UTC).isoformat()
        payload["error"] = None
        finalize_batch(settings, payload)
        return payload
    except Exception as exc:
        payload = load_batch(settings, batch_id)
        payload["status"] = "failed"
        payload["completed"] = len(results)
        payload["count"] = len(results)
        payload["results"] = results
        payload["error"] = str(exc)
        payload["finished_at"] = datetime.now(tz=UTC).isoformat()
        finalize_batch(settings, payload)
        return payload


def format_batch_status(
    payload: dict[str, Any],
    settings: Settings,
    *,
    async_started: bool = False,
) -> dict[str, Any]:
    batch_id = payload["batch_id"]
    batch_dir = settings.runs_path / f"batch-{batch_id}"
    response = {
        "batch_id": batch_id,
        "status": payload["status"],
        "count": payload.get("count", 0),
        "completed": payload.get("completed", 0),
        "total": payload.get("total", 0),
        "pipeline_id": payload["pipeline_id"],
        "results": payload.get("results", []),
        "batch_json_path": str(batch_dir / "batch.json"),
        "batch_summary_path": str(batch_dir / "summary.md"),
        "error": payload.get("error"),
        "async": async_started or payload.get("async_mode", False),
    }
    if payload["status"] in {"completed", "failed", "cancelled"}:
        response["finished_at"] = payload.get("finished_at")
    return response
