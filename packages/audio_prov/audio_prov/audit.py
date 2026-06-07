from __future__ import annotations

import json
from pathlib import Path

from audio_prov.config import Settings
from audio_prov.models import ProvenanceReport, RunAudit


def write_run_artifacts(
    settings: Settings,
    audit: RunAudit,
    report: ProvenanceReport,
) -> dict[str, Path]:
    run_dir = settings.runs_path / audit.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    report_path = run_dir / "report.json"
    summary_path = run_dir / "summary.md"
    audit_path = run_dir / "run.json"

    report_path.write_text(
        json.dumps(report.model_dump(), indent=2, default=str),
        encoding="utf-8",
    )
    audit_path.write_text(
        json.dumps(audit.model_dump(), indent=2, default=str),
        encoding="utf-8",
    )
    summary_path.write_text(_render_summary(report), encoding="utf-8")

    return {"report": report_path, "summary": summary_path, "audit": audit_path}


def write_batch_artifacts(
    settings: Settings,
    *,
    batch_id: str,
    pipeline_id: str,
    results: list[dict],
    preset: str | None = None,
    status: str = "completed",
    total: int | None = None,
    completed: int | None = None,
    error: str | None = None,
    async_mode: bool = False,
    started_at: str | None = None,
    finished_at: str | None = None,
) -> dict[str, Path]:
    batch_dir = settings.runs_path / f"batch-{batch_id}"
    batch_dir.mkdir(parents=True, exist_ok=True)

    summary_path = batch_dir / "summary.md"
    batch_path = batch_dir / "batch.json"

    payload = {
        "batch_id": batch_id,
        "status": status,
        "pipeline_id": pipeline_id,
        "preset": preset,
        "total": total if total is not None else len(results),
        "completed": completed if completed is not None else len(results),
        "count": len(results),
        "results": results,
        "error": error,
        "async_mode": async_mode,
        "started_at": started_at,
        "finished_at": finished_at,
    }
    _write_batch_files(settings, payload)
    return {"summary": summary_path, "batch": batch_path}


def init_batch_state(
    settings: Settings,
    *,
    batch_id: str,
    pipeline_id: str,
    preset: str | None,
    total: int,
    async_mode: bool = False,
) -> dict[str, Path]:
    from datetime import UTC, datetime

    return write_batch_artifacts(
        settings,
        batch_id=batch_id,
        pipeline_id=pipeline_id,
        results=[],
        preset=preset,
        status="pending" if async_mode else "running",
        total=total,
        completed=0,
        async_mode=async_mode,
        started_at=datetime.now(tz=UTC).isoformat(),
    )


def save_batch_state(settings: Settings, payload: dict) -> None:
    _write_batch_files(settings, payload)


def finalize_batch(settings: Settings, payload: dict) -> dict[str, Path]:
    batch_dir = settings.runs_path / f"batch-{payload['batch_id']}"
    batch_dir.mkdir(parents=True, exist_ok=True)
    _write_batch_files(settings, payload)
    return {"summary": batch_dir / "summary.md", "batch": batch_dir / "batch.json"}


def load_batch(settings: Settings, batch_id: str) -> dict:
    batch_path = settings.runs_path / f"batch-{batch_id}" / "batch.json"
    if not batch_path.exists():
        from audio_prov.errors import BatchNotFoundError

        raise BatchNotFoundError(batch_id)
    return json.loads(batch_path.read_text(encoding="utf-8"))


def _write_batch_files(settings: Settings, payload: dict) -> None:
    batch_dir = settings.runs_path / f"batch-{payload['batch_id']}"
    batch_dir.mkdir(parents=True, exist_ok=True)
    batch_path = batch_dir / "batch.json"
    summary_path = batch_dir / "summary.md"
    tmp_path = batch_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    tmp_path.replace(batch_path)
    summary_path.write_text(_render_batch_summary(payload), encoding="utf-8")


def load_run(settings: Settings, run_id: str) -> dict:
    run_dir = settings.runs_path / run_id
    audit_path = run_dir / "run.json"
    report_path = run_dir / "report.json"
    summary_path = run_dir / "summary.md"
    if not audit_path.exists():
        raise FileNotFoundError(f"Run not found: {run_id}")
    result = {
        "audit": json.loads(audit_path.read_text(encoding="utf-8")),
        "report_paths": {
            "report": str(report_path) if report_path.exists() else None,
            "summary": str(summary_path) if summary_path.exists() else None,
            "audit": str(audit_path),
        },
    }
    if report_path.exists():
        result["report"] = json.loads(report_path.read_text(encoding="utf-8"))
    return result


def _render_summary(report: ProvenanceReport) -> str:
    insp = report.structural.inspect
    verified_detail = _verified_summary(report)
    lines = [
        f"# Provenance summary — {report.asset_id}",
        "",
        "| Signal | Status | Detail |",
        "|--------|--------|--------|",
        f"| Structural | OK | {insp.format_profile or insp.codec}, {insp.duration_sec or '?'}s |",
        f"| Verified | {report.verified.status} | {verified_detail} |",
    ]
    if report.simulated:
        before = report.simulated.before.status if report.simulated.before else "n/a"
        after = report.simulated.after.status if report.simulated.after else "n/a"
        lines.append(
            f"| Simulated ({report.simulated.preset}) | {before} → {after} | distribution stress |"
        )
    if report.inferred:
        signal_count = sum(len(r.signals) for r in report.inferred.results)
        if signal_count:
            inferred_detail = (
                f"{len(report.inferred.results)} plugin(s), {signal_count} hint(s)"
            )
        else:
            inferred_detail = "no tag/filename hints; external detector not configured"
        lines.append(f"| Inferred | {report.inferred.status} | {inferred_detail} |")
    else:
        lines.append("| Inferred | disabled | AUDIO_PROV_DETECT_PLUGINS empty |")
    if report.structural.tags.tags:
        tag_items = list(report.structural.tags.tags.items())[:3]
        tag_preview = ", ".join(f"{k}={v}" for k, v in tag_items)
        lines.append(f"| Tags | present | {tag_preview} |")
    lines.extend(["", report.disclaimer])
    if report.verified.status.value == "absent":
        lines.extend(
            [
                "",
                "**Note:** Absent credentials mean no C2PA or sidecar manifest was found. "
                "This does not indicate whether the audio is AI-generated or human-recorded.",
            ]
        )
    return "\n".join(lines)


def _verified_summary(report: ProvenanceReport) -> str:
    n = len(report.verified.results)
    if report.verified.status.value == "absent":
        return f"{n} checker(s); no credentials found"
    if report.verified.status.value == "valid":
        return f"{n} checker(s); at least one valid credential"
    return f"{n} checker(s); credential validation failed"


def _render_batch_summary(payload: dict) -> str:
    batch_id = payload["batch_id"]
    pipeline_id = payload["pipeline_id"]
    results = payload["results"]
    status = payload.get("status", "completed")
    total = payload.get("total", len(results))
    completed = payload.get("completed", len(results))
    lines = [
        f"# Batch provenance summary — {batch_id}",
        "",
        f"Pipeline: `{pipeline_id}`",
        f"Status: **{status}** ({completed}/{total} files)",
        "",
    ]
    if status in {"running", "pending", "cancelling"}:
        lines.append("_Batch in progress — refresh or poll `get_batch_run`._")
        lines.append("")
    if payload.get("error"):
        lines.append(f"**Error:** {payload['error']}")
        lines.append("")

    if not results:
        if status == "completed":
            lines.append("_No matching workspace audio files._")
        return "\n".join(lines)

    lines.extend(
        [
            "| File | Asset | Verified | Inferred | Run |",
            "|------|-------|----------|----------|-----|",
        ]
    )
    for item in results:
        summary = item["summary"]
        inferred = summary.get("inferred_status", "n/a")
        lines.append(
            f"| {item['filename']} | {item['asset_id']} | "
            f"{summary.get('verified_status', 'n/a')} | {inferred} | "
            f"`{item['run_id']}` |"
        )

    lines.extend(
        [
            "",
            "Individual run reports are under `runs/<run_id>/`.",
            "",
            "Absent credentials do not prove synthetic origin — see per-run disclaimers.",
        ]
    )
    return "\n".join(lines)
