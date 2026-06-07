from __future__ import annotations

import json
from typing import Any

from audio_prov import __version__ as core_version
from audio_prov.assets import AssetStore
from audio_prov.audit import load_batch, load_run
from audio_prov.batch import (
    batch_analyze_workspace,
    cancel_batch_job,
    format_batch_status,
    start_batch_job,
)
from audio_prov.config import get_settings
from audio_prov.errors import check_setup
from audio_prov.models import Asset
from audio_prov.pipeline import PipelineRunner
from audio_prov.plugins.transform_ffmpeg import list_presets
from audio_prov.plugins.verify_demo import sign_demo_manifest
from audio_prov.registry import default_registry
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "audio-provenance",
    instructions=(
        "Deterministic audio provenance analysis for real-world AI audio in the local workspace. "
        "Workflow: list_workspace_files → register_workspace_file → analyze_ai_audio (tool). "
        "Do NOT pass MCP prompt names (analyze-ai-audio) to provenance_run — use the "
        "analyze_ai_audio tool or pipeline_id provenance-analysis@1. "
        "Never claim absent credentials prove synthetic origin."
    ),
)

_settings = get_settings()
_store = AssetStore(_settings)
_runner = PipelineRunner(settings=_settings, asset_store=_store)
_registry = default_registry(_settings)

# MCP prompt names are NOT pipeline IDs — map common mistakes.
PIPELINE_ALIASES: dict[str, str] = {
    "analyze-ai-audio": "provenance-analysis@1",
    "analyze_ai_audio": "provenance-analysis@1",
    "real-world-stress-test": "real-world-analysis@1",
    "real_world_stress_test": "real-world-analysis@1",
    "inspect-only": "inspect-only@1",
    "provenance-analysis": "provenance-analysis@1",
    "real-world-analysis": "real-world-analysis@1",
}

VALID_PIPELINE_IDS = (
    "inspect-only@1",
    "provenance-analysis@1",
    "real-world-analysis@1",
)


def _resolve_pipeline_id(pipeline_id: str) -> str:
    return PIPELINE_ALIASES.get(pipeline_id, pipeline_id)


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


def _resolve_asset(ref: str) -> Asset:
    return _store.resolve_asset_ref(ref)


@mcp.tool()
def check_environment() -> str:
    """Check ffmpeg/ffprobe (and optional c2patool) before running analysis."""
    return _json(check_setup(_settings))


@mcp.tool()
def describe_pipeline(pipeline_id: str) -> str:
    """Describe pipeline steps for a given pipeline_id (e.g. provenance-analysis@1)."""
    resolved = _resolve_pipeline_id(pipeline_id)
    return _json(_runner.describe_pipeline(resolved))


@mcp.tool()
def list_workspace_files(glob_pattern: str | None = None) -> str:
    """List audio files in the configured workspace directory."""
    return _json(_store.list_workspace_files(glob_pattern))


@mcp.tool()
def register_workspace_file(filename: str, user_hints_json: str | None = None) -> str:
    """Register a workspace audio file for analysis. Returns asset_id and content hash."""
    hints = json.loads(user_hints_json) if user_hints_json else None
    asset = _store.register_workspace_file(filename, user_hints=hints)
    return _json(asset.model_dump())


@mcp.tool()
def list_fixtures() -> str:
    """List committed test fixtures available for regression demos."""
    return _json(_store.list_fixtures())


@mcp.tool()
def inspect_audio(asset_ref: str) -> str:
    """Inspect structural properties (codec, duration, hash).

    asset_ref: asset_id (e.g. wot_s), workspace filename (e.g. WOT_s.wav), or path.
    """
    asset = _resolve_asset(asset_ref)
    path = _store.resolve_path(asset)
    plugin = _runner.registry.get_inspect("inspect.ffprobe")
    tags = _runner.registry.get_metadata("metadata.tags")
    return _json(
        {
            "inspect": plugin.inspect(path).model_dump(),
            "tags": tags.extract(path).model_dump(),
        }
    )


@mcp.tool()
def verify_provenance(asset_ref: str) -> str:
    """Verify credentials (demo sidecar + C2PA if available).

    asset_ref: asset_id, workspace filename, or path.
    """
    asset = _resolve_asset(asset_ref)
    return _json({"asset_id": asset.asset_id, "results": _runner.verify_asset(asset.asset_id)})


@mcp.tool()
def simulate_distribution(asset_ref: str, preset: str = "aac128") -> str:
    """Apply a distribution-style transcode preset to an asset."""
    asset = _resolve_asset(asset_ref)
    return _json(_runner.simulate_distribution(asset.asset_id, preset))


@mcp.tool()
def list_pipelines() -> str:
    """List valid pipeline_id values for provenance_run (not MCP prompt names)."""
    return _json({"pipeline_ids": list(VALID_PIPELINE_IDS), "aliases": PIPELINE_ALIASES})


@mcp.tool()
def provenance_run(
    pipeline_id: str,
    asset_ref: str,
    preset: str | None = None,
) -> str:
    """Run a provenance pipeline.

    Valid pipeline_id values ONLY:
    - provenance-analysis@1 (inspect + verify + report)
    - real-world-analysis@1 (inspect + verify + transcode + verify + report)
    - inspect-only@1

    NOT valid: analyze-ai-audio (that is an MCP prompt name — use analyze_ai_audio tool).
    """
    resolved = _resolve_pipeline_id(pipeline_id)
    asset = _resolve_asset(asset_ref)
    options = {"preset": preset} if preset else {}
    audit, summary = _runner.run(resolved, asset.asset_id, options=options)
    return _json({"audit": audit.model_dump(), "summary": summary})


@mcp.tool()
def analyze_ai_audio(asset_ref: str) -> str:
    """Run full provenance analysis (provenance-analysis@1).

    asset_ref: asset_id (e.g. wot_s), workspace filename (e.g. WOT_s.wav), or path.
    Auto-registers workspace files if needed.
    """
    asset = _resolve_asset(asset_ref)
    audit, summary = _runner.run("provenance-analysis@1", asset.asset_id)
    return _json({"audit": audit.model_dump(), "summary": summary})


@mcp.tool()
def real_world_stress_test(asset_ref: str, preset: str = "aac128") -> str:
    """Run distribution stress test (real-world-analysis@1)."""
    asset = _resolve_asset(asset_ref)
    audit, summary = _runner.run(
        "real-world-analysis@1", asset.asset_id, options={"preset": preset}
    )
    return _json({"audit": audit.model_dump(), "summary": summary})


@mcp.tool()
def analyze_workspace(
    pipeline_id: str = "provenance-analysis@1",
    preset: str | None = None,
    glob_pattern: str | None = None,
) -> str:
    """Analyze every audio file in workspace/ (blocking batch provenance run)."""
    return _json(
        batch_analyze_workspace(
            _store,
            _runner,
            pipeline_id=pipeline_id,
            preset=preset,
            glob_pattern=glob_pattern,
        )
    )


@mcp.tool()
def analyze_workspace_async(
    pipeline_id: str = "provenance-analysis@1",
    preset: str | None = None,
    glob_pattern: str | None = None,
) -> str:
    """Start a background batch job over workspace/; poll with get_batch_run."""
    return _json(
        start_batch_job(
            _store,
            _runner,
            pipeline_id=pipeline_id,
            preset=preset,
            glob_pattern=glob_pattern,
        )
    )


@mcp.tool()
def get_batch_run(batch_id: str) -> str:
    """Poll async batch status and partial/final results."""
    payload = load_batch(_settings, batch_id)
    return _json(format_batch_status(payload, _settings))


@mcp.tool()
def cancel_batch_run(batch_id: str) -> str:
    """Request cancellation of a running async batch job."""
    return _json(cancel_batch_job(_settings, batch_id))


@mcp.tool()
def sign_demo_sidecar(filename: str, claims_json: str = '{"synthetic": true}') -> str:
    """Write a demo Ed25519 sidecar manifest for a workspace file (dev keys only)."""
    asset = _resolve_asset(filename)
    path = _store.resolve_path(asset)
    claims = json.loads(claims_json)
    sign_demo_manifest(path, claims)
    return _json(
        {
            "asset_id": asset.asset_id,
            "filename": filename,
            "path": str(path),
            "claims": claims,
        }
    )


@mcp.tool()
def sign_c2pa_manifest(
    filename: str,
    manifest_path: str | None = None,
    output_path: str | None = None,
) -> str:
    """Embed a C2PA manifest in a workspace audio file (development cert by default)."""
    from pathlib import Path

    asset = _resolve_asset(filename)
    path = _store.resolve_path(asset)
    plugin = _registry.get_sign("sign.c2pa")
    payload = plugin.sign(
        path,
        manifest_path=Path(manifest_path) if manifest_path else None,
        output_path=Path(output_path) if output_path else None,
    )
    payload["asset_id"] = asset.asset_id
    payload["filename"] = filename
    return _json(payload)


@mcp.tool()
def get_run(run_id: str) -> str:
    """Load audit log and report paths for a prior pipeline run."""
    return _json(load_run(_settings, run_id))


@mcp.resource("config://capabilities")
def capabilities_resource() -> str:
    registry = default_registry(_settings)
    return _json(
        {
            "core_version": core_version,
            "workspace": str(_settings.workspace_path),
            "plugins": registry.list_capabilities(),
            "pipelines": sorted(p.name for p in _settings.pipelines_path.glob("*.yaml")),
        }
    )


@mcp.resource("config://pipelines")
def pipelines_resource() -> str:
    return _json(_runner.list_pipeline_descriptions())


@mcp.resource("config://transform-presets")
def transform_presets_resource() -> str:
    return _json([p.model_dump() for p in list_presets()])


@mcp.resource("schema://report/v1")
def report_schema_resource() -> str:
    path = _settings.schemas_path / "report" / "v1.json"
    return path.read_text(encoding="utf-8")


@mcp.resource("schema://claims/v1")
def claims_schema_resource() -> str:
    path = _settings.schemas_path / "claims" / "v1.json"
    return path.read_text(encoding="utf-8")


@mcp.prompt()
def analyze_ai_audio_prompt(asset_id: str) -> str:
    """Summarize a completed analyze_ai_audio tool run."""
    return (
        f"Call the analyze_ai_audio tool with asset_id='{asset_id}' (NOT provenance_run). "
        "Then summarize results in a markdown table: Structural, Verified, Simulated, Inferred. "
        "If verified is absent, credentials are missing — not proof of synthetic origin."
    )


@mcp.prompt()
def real_world_stress_test_prompt(asset_id: str, preset: str = "aac128") -> str:
    """Summarize a completed real_world_stress_test tool run."""
    return (
        f"Call the real_world_stress_test tool with asset_id='{asset_id}' and preset='{preset}'. "
        "Compare verified status before and after simulated distribution."
    )


@mcp.prompt()
def explain_provenance_report(run_id: str) -> str:
    """Explain a completed run report in plain language."""
    return (
        f"Call get_run for run_id='{run_id}' and explain structural, verified, "
        "and simulated blocks. "
        "Do not invent claims not present in the report JSON."
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
