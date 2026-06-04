from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from audio_prov.config import Settings, get_settings
from audio_prov.models import (
    Asset,
    InspectResult,
    ProvenanceReport,
    TagResult,
    TransformResult,
    VerifiedBlock,
    VerifyResult,
    VerifyStatus,
)


@dataclass
class PipelineContext:
    asset: Asset
    settings: Settings
    pipeline_id: str
    run_id: str
    options: dict[str, Any] = field(default_factory=dict)
    inspect_result: InspectResult | None = None
    tag_result: TagResult | None = None
    verify_results: list[VerifyResult] = field(default_factory=list)
    verify_before: list[VerifyResult] = field(default_factory=list)
    verify_after: list[VerifyResult] = field(default_factory=list)
    transform_result: TransformResult | None = None
    current_path: Path | None = None
    report: ProvenanceReport | None = None

    @property
    def active_path(self) -> Path:
        if self.current_path is not None:
            return self.current_path
        return Path(self.asset.path)


class InspectPlugin(Protocol):
    id: str
    version: str

    def inspect(self, path: Path) -> InspectResult: ...


class MetadataPlugin(Protocol):
    id: str
    version: str

    def extract(self, path: Path) -> TagResult: ...


class VerifyPlugin(Protocol):
    id: str
    version: str

    def verify(self, path: Path) -> VerifyResult: ...


class TransformPlugin(Protocol):
    id: str
    version: str

    def transform(self, path: Path, preset: str, output_dir: Path) -> TransformResult: ...


class ReportPlugin(Protocol):
    id: str
    version: str

    def build(self, ctx: PipelineContext) -> ProvenanceReport: ...


class PluginRegistry:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._inspect: dict[str, InspectPlugin] = {}
        self._metadata: dict[str, MetadataPlugin] = {}
        self._verify: dict[str, VerifyPlugin] = {}
        self._transform: dict[str, TransformPlugin] = {}
        self._report: dict[str, ReportPlugin] = {}

    def register_inspect(self, plugin: InspectPlugin) -> None:
        self._inspect[plugin.id] = plugin

    def register_metadata(self, plugin: MetadataPlugin) -> None:
        self._metadata[plugin.id] = plugin

    def register_verify(self, plugin: VerifyPlugin) -> None:
        self._verify[plugin.id] = plugin

    def register_transform(self, plugin: TransformPlugin) -> None:
        self._transform[plugin.id] = plugin

    def register_report(self, plugin: ReportPlugin) -> None:
        self._report[plugin.id] = plugin

    def get_inspect(self, plugin_id: str) -> InspectPlugin:
        return self._inspect[_short_id(plugin_id)]

    def get_metadata(self, plugin_id: str) -> MetadataPlugin:
        return self._metadata[_short_id(plugin_id)]

    def get_verify(self, plugin_id: str) -> VerifyPlugin:
        return self._verify[_short_id(plugin_id)]

    def get_transform(self, plugin_id: str) -> TransformPlugin:
        return self._transform[_short_id(plugin_id)]

    def get_report(self, plugin_id: str) -> ReportPlugin:
        return self._report[_short_id(plugin_id)]

    def list_capabilities(self) -> dict[str, Any]:
        return {
            "inspect": {k: v.version for k, v in self._inspect.items()},
            "metadata": {k: v.version for k, v in self._metadata.items()},
            "verify": {k: v.version for k, v in self._verify.items()},
            "transform": {k: v.version for k, v in self._transform.items()},
            "report": {k: v.version for k, v in self._report.items()},
        }


def _short_id(plugin_id: str) -> str:
    return plugin_id.split(".")[-1] if "." in plugin_id else plugin_id


def merge_verified(results: list[VerifyResult]) -> VerifiedBlock:
    if not results:
        return VerifiedBlock(status=VerifyStatus.ABSENT, results=[])
    if any(r.status == VerifyStatus.INVALID for r in results):
        status = VerifyStatus.INVALID
    elif any(r.status == VerifyStatus.VALID for r in results):
        status = VerifyStatus.VALID
    else:
        status = VerifyStatus.ABSENT
    return VerifiedBlock(status=status, results=results)


def default_registry(settings: Settings | None = None) -> PluginRegistry:
    from audio_prov.plugins.inspect_ffprobe import FfprobeInspectPlugin
    from audio_prov.plugins.metadata_tags import FfprobeMetadataPlugin
    from audio_prov.plugins.report_default import DefaultReportPlugin
    from audio_prov.plugins.transform_ffmpeg import FfmpegTransformPlugin
    from audio_prov.plugins.verify_c2pa import C2paVerifyPlugin
    from audio_prov.plugins.verify_demo import DemoVerifyPlugin

    settings = settings or get_settings()
    registry = PluginRegistry(settings)
    registry.register_inspect(FfprobeInspectPlugin(settings))
    registry.register_metadata(FfprobeMetadataPlugin(settings))
    registry.register_verify(DemoVerifyPlugin())
    registry.register_verify(C2paVerifyPlugin(settings))
    registry.register_transform(FfmpegTransformPlugin(settings))
    registry.register_report(DefaultReportPlugin())
    return registry
