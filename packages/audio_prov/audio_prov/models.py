from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class OriginContext(StrEnum):
    USER_PROVIDED = "user_provided"
    FIXTURE = "fixture"
    GENERATED = "generated"


class VerifyStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    ABSENT = "absent"


class Asset(BaseModel):
    asset_id: str
    path: str
    content_hash: str
    origin_context: OriginContext
    format_profile: str | None = None
    user_hints: dict[str, Any] = Field(default_factory=dict)


class InspectResult(BaseModel):
    duration_sec: float | None = None
    sample_rate: int | None = None
    channels: int | None = None
    codec: str | None = None
    bit_rate: int | None = None
    format_name: str | None = None
    format_profile: str | None = None
    content_hash: str


class TagResult(BaseModel):
    tags: dict[str, str] = Field(default_factory=dict)


class VerifyResult(BaseModel):
    plugin_id: str
    plugin_version: str
    status: VerifyStatus
    details: dict[str, Any] = Field(default_factory=dict)


class TransformResult(BaseModel):
    output_path: str
    preset: str
    bytes_out: int


class StructuralBlock(BaseModel):
    inspect: InspectResult
    tags: TagResult = Field(default_factory=TagResult)


class VerifiedBlock(BaseModel):
    status: VerifyStatus
    results: list[VerifyResult] = Field(default_factory=list)


class SimulatedBlock(BaseModel):
    preset: str | None = None
    derived_path: str | None = None
    before: VerifiedBlock | None = None
    after: VerifiedBlock | None = None


class ProvenanceReport(BaseModel):
    report_schema_version: str = "1.0"
    asset_id: str
    content_hash: str
    pipeline_id: str
    run_id: str
    structural: StructuralBlock
    verified: VerifiedBlock
    simulated: SimulatedBlock | None = None
    inferred: dict[str, Any] | None = None
    user_hints: dict[str, Any] = Field(default_factory=dict)
    disclaimer: str = (
        "Analysis reports technical evidence only. Absent credentials do not prove "
        "synthetic origin. Demo sidecar manifests use development keys only."
    )


class StepAudit(BaseModel):
    plugin_id: str
    plugin_version: str
    input_hash: str | None = None
    output: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int = 0
    error: str | None = None


class RunAudit(BaseModel):
    run_id: str
    pipeline_id: str
    asset_id: str
    steps: list[StepAudit] = Field(default_factory=list)
    report_path: str | None = None
    summary_path: str | None = None


class TransformPresetInfo(BaseModel):
    id: str
    description: str
    models: str
