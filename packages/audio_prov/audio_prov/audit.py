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
