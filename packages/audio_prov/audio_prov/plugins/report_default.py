from __future__ import annotations

from audio_prov.models import (
    ProvenanceReport,
    SimulatedBlock,
    StructuralBlock,
    TagResult,
)
from audio_prov.registry import PipelineContext, merge_verified


class DefaultReportPlugin:
    id = "default"
    version = "0.1.0"

    def build(self, ctx: PipelineContext) -> ProvenanceReport:
        if ctx.inspect_result is None:
            raise RuntimeError("Report requires inspect result")

        tags = ctx.tag_result or TagResult()
        structural = StructuralBlock(inspect=ctx.inspect_result, tags=tags)

        if ctx.verify_after:
            verified = merge_verified(ctx.verify_after)
            simulated = SimulatedBlock(
                preset=ctx.transform_result.preset if ctx.transform_result else None,
                derived_path=ctx.transform_result.output_path if ctx.transform_result else None,
                before=merge_verified(ctx.verify_before),
                after=merge_verified(ctx.verify_after),
            )
        else:
            results = ctx.verify_before or ctx.verify_results
            verified = merge_verified(results)
            simulated = None

        return ProvenanceReport(
            asset_id=ctx.asset.asset_id,
            content_hash=ctx.inspect_result.content_hash,
            pipeline_id=ctx.pipeline_id,
            run_id=ctx.run_id,
            structural=structural,
            verified=verified,
            simulated=simulated,
            inferred=None,
            user_hints=ctx.asset.user_hints,
        )
