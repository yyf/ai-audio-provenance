from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from audio_prov.assets import AssetStore
from audio_prov.audit import write_run_artifacts
from audio_prov.config import Settings, get_settings
from audio_prov.models import RunAudit, StepAudit, VerifyResult
from audio_prov.registry import PipelineContext, PluginRegistry, default_registry


@dataclass
class PipelineDefinition:
    id: str
    steps: list[dict[str, Any]]


class PipelineRunner:
    def __init__(
        self,
        settings: Settings | None = None,
        registry: PluginRegistry | None = None,
        asset_store: AssetStore | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.registry = registry or default_registry(self.settings)
        self.asset_store = asset_store or AssetStore(self.settings)

    def load_pipeline(self, pipeline_id: str) -> PipelineDefinition:
        path = self.settings.pipelines_path / f"{pipeline_id.split('@')[0]}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Pipeline not found: {pipeline_id}")
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if data["id"] != pipeline_id:
            raise ValueError(f"Pipeline id mismatch: expected {pipeline_id}, got {data['id']}")
        return PipelineDefinition(id=data["id"], steps=data["steps"])

    def run_all_verifiers(self, path: Path) -> list[VerifyResult]:
        results: list[VerifyResult] = []
        for plugin_id in self.settings.verify_plugins:
            try:
                plugin = self.registry.get_verify(plugin_id)
            except KeyError:
                continue
            results.append(plugin.verify(path))
        return results

    def verify_asset(self, asset_id: str) -> list[dict[str, Any]]:
        asset = self.asset_store.get_asset(asset_id)
        path = self.asset_store.resolve_path(asset)
        return [result.model_dump() for result in self.run_all_verifiers(path)]

    def simulate_distribution(
        self,
        asset_id: str,
        preset: str,
    ) -> dict[str, Any]:
        asset = self.asset_store.get_asset(asset_id)
        path = self.asset_store.resolve_path(asset)
        plugin = self.registry.get_transform("transform.ffmpeg")
        output_dir = self.settings.runs_path / "simulations" / asset_id
        output_dir.mkdir(parents=True, exist_ok=True)
        result = plugin.transform(path, preset, output_dir)
        return result.model_dump()

    def run(
        self,
        pipeline_id: str,
        asset_id: str,
        options: dict[str, Any] | None = None,
    ) -> tuple[RunAudit, dict[str, Any]]:
        pipeline = self.load_pipeline(pipeline_id)
        asset = self.asset_store.get_asset(asset_id)
        run_id = str(uuid.uuid4())
        ctx = PipelineContext(
            asset=asset,
            settings=self.settings,
            pipeline_id=pipeline_id,
            run_id=run_id,
            options=options or {},
            current_path=self.asset_store.resolve_path(asset),
        )
        audit = RunAudit(run_id=run_id, pipeline_id=pipeline_id, asset_id=asset_id)

        for step in pipeline.steps:
            plugin_ref = step["plugin"]
            params = step.get("params", {})
            started = time.perf_counter()
            step_audit = StepAudit(
                plugin_id=plugin_ref,
                plugin_version="unknown",
                input_hash=ctx.asset.content_hash,
            )
            try:
                self._execute_step(ctx, audit, step_audit, plugin_ref, params, run_id)
            except Exception as exc:
                step_audit.error = str(exc)
                step_audit.duration_ms = int((time.perf_counter() - started) * 1000)
                audit.steps.append(step_audit)
                raise
            step_audit.duration_ms = int((time.perf_counter() - started) * 1000)
            audit.steps.append(step_audit)

        if ctx.report is None:
            raise RuntimeError("Pipeline completed without report step")

        paths = write_run_artifacts(self.settings, audit, ctx.report)
        audit.report_path = str(paths["report"])
        audit.summary_path = str(paths["summary"])

        summary = {
            "run_id": run_id,
            "pipeline_id": pipeline_id,
            "asset_id": asset_id,
            "verified_status": ctx.report.verified.status,
            "format_profile": ctx.report.structural.inspect.format_profile,
            "report_path": audit.report_path,
            "summary_path": audit.summary_path,
        }
        return audit, summary

    def _execute_step(
        self,
        ctx: PipelineContext,
        audit: RunAudit,
        step_audit: StepAudit,
        plugin_ref: str,
        params: dict[str, Any],
        run_id: str,
    ) -> None:
        if plugin_ref.startswith("inspect."):
            plugin = self.registry.get_inspect(plugin_ref)
            step_audit.plugin_version = plugin.version
            ctx.inspect_result = plugin.inspect(ctx.active_path)
            ctx.asset.format_profile = ctx.inspect_result.format_profile
            step_audit.output = ctx.inspect_result.model_dump()
            return

        if plugin_ref.startswith("metadata."):
            plugin = self.registry.get_metadata(plugin_ref)
            step_audit.plugin_version = plugin.version
            ctx.tag_result = plugin.extract(ctx.active_path)
            step_audit.output = ctx.tag_result.model_dump()
            return

        if plugin_ref == "verify.all":
            results = self.run_all_verifiers(ctx.active_path)
            if ctx.transform_result is None and not ctx.verify_before:
                ctx.verify_before = results
            elif ctx.transform_result is not None:
                ctx.verify_after = results
            ctx.verify_results = results
            step_audit.output = {"results": [r.model_dump() for r in results]}
            step_audit.plugin_version = "aggregate"
            return

        if plugin_ref == "verify.snapshot_before":
            ctx.verify_before = list(ctx.verify_results)
            step_audit.output = {"captured": len(ctx.verify_before)}
            step_audit.plugin_version = "aggregate"
            return

        if plugin_ref.startswith("verify."):
            plugin = self.registry.get_verify(plugin_ref)
            step_audit.plugin_version = plugin.version
            result = plugin.verify(ctx.active_path)
            ctx.verify_results.append(result)
            step_audit.output = result.model_dump()
            return

        if plugin_ref.startswith("transform."):
            plugin = self.registry.get_transform(plugin_ref)
            step_audit.plugin_version = plugin.version
            preset = params.get("preset") or ctx.options.get(
                "preset", self.settings.default_transform_preset
            )
            output_dir = self.settings.runs_path / run_id / "derived"
            output_dir.mkdir(parents=True, exist_ok=True)
            ctx.transform_result = plugin.transform(ctx.active_path, preset, output_dir)
            ctx.current_path = Path(ctx.transform_result.output_path)
            step_audit.output = ctx.transform_result.model_dump()
            return

        if plugin_ref.startswith("report."):
            plugin = self.registry.get_report(plugin_ref)
            step_audit.plugin_version = plugin.version
            ctx.report = plugin.build(ctx)
            step_audit.output = {"report_schema_version": ctx.report.report_schema_version}
            return

        raise ValueError(f"Unknown step plugin: {plugin_ref}")
