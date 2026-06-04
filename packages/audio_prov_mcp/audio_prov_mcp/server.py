from __future__ import annotations

import json
from typing import Any

from audio_prov import __version__ as core_version
from audio_prov.assets import AssetStore
from audio_prov.audit import load_run
from audio_prov.config import get_settings
from audio_prov.pipeline import PipelineRunner
from audio_prov.plugins.transform_ffmpeg import list_presets
from audio_prov.registry import default_registry
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "audio-provenance",
    instructions=(
        "Deterministic audio provenance analysis for real-world AI audio in the local workspace. "
        "Use list_workspace_files and register_workspace_file before analysis. "
        "Never claim absent credentials prove synthetic origin. "
        "Demo manifests use development keys only."
    ),
)

_settings = get_settings()
_runner = PipelineRunner(settings=_settings)
_store = AssetStore(_settings)


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


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
def inspect_audio(asset_id: str) -> str:
    """Inspect structural properties (codec, duration, hash) for a registered asset."""
    asset = _store.get_asset(asset_id)
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
def verify_provenance(asset_id: str) -> str:
    """Verify credentials (demo sidecar + C2PA if available) for an asset."""
    return _json({"results": _runner.verify_asset(asset_id)})


@mcp.tool()
def simulate_distribution(asset_id: str, preset: str = "aac128") -> str:
    """Apply a distribution-style transcode preset to an asset."""
    return _json(_runner.simulate_distribution(asset_id, preset))


@mcp.tool()
def provenance_run(
    pipeline_id: str,
    asset_id: str,
    preset: str | None = None,
) -> str:
    """Run a provenance pipeline (e.g. provenance-analysis@1, real-world-analysis@1)."""
    options = {"preset": preset} if preset else {}
    audit, summary = _runner.run(pipeline_id, asset_id, options=options)
    return _json({"audit": audit.model_dump(), "summary": summary})


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
def analyze_ai_audio(asset_id: str) -> str:
    """Run provenance-analysis@1 and summarize structural + verified blocks."""
    return (
        f"Run provenance_run with pipeline_id='provenance-analysis@1' and asset_id='{asset_id}'. "
        "Then summarize results in a markdown table separating Structural, Verified, and Inferred. "
        "If verified is absent, explain that credentials are missing — "
        "not proof of synthetic origin."
    )


@mcp.prompt()
def real_world_stress_test(asset_id: str, preset: str = "aac128") -> str:
    """Run real-world-analysis@1 with distribution stress preset."""
    return (
        f"Run provenance_run with pipeline_id='real-world-analysis@1', asset_id='{asset_id}', "
        f"preset='{preset}'. Compare verified status before and after simulated distribution."
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
