from pathlib import Path

import pytest
from audio_prov.assets import AssetStore
from audio_prov.config import Settings
from audio_prov.guards import GuardError, ensure_allowed
from audio_prov.pipeline import PipelineRunner
from audio_prov.plugins.verify_demo import DemoVerifyPlugin, sign_demo_manifest


@pytest.fixture
def settings() -> Settings:
    from audio_prov.config import find_project_root

    root = find_project_root()
    return Settings(project_root=root)


@pytest.fixture
def runner(settings: Settings) -> PipelineRunner:
    return PipelineRunner(settings=settings)


def test_guard_rejects_outside_root(settings: Settings) -> None:
    with pytest.raises(GuardError):
        ensure_allowed(settings.project_root / "etc" / "passwd", settings)


def test_demo_sign_verify_roundtrip(settings: Settings, tmp_path) -> None:
    import math
    import struct
    import wave

    path = tmp_path / "test.wav"
    sample_rate = 44100
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        for i in range(sample_rate // 10):
            value = int(32767 * 0.2 * math.sin(2 * math.pi * 440 * i / sample_rate))
            wf.writeframes(struct.pack("<h", value))

    sign_demo_manifest(path, {"synthetic": True, "generator": "test"})
    plugin = DemoVerifyPlugin()
    result = plugin.verify(path)
    assert result.status.value == "valid"


def test_provenance_analysis_on_fixture(runner: PipelineRunner) -> None:
    audit, summary = runner.run("provenance-analysis@1", "tone-wav")
    assert summary["verified_status"] in {"valid", "invalid", "absent"}
    assert audit.report_path is not None
    import json
    from pathlib import Path

    report = json.loads(Path(audit.report_path).read_text(encoding="utf-8"))
    assert report["inferred"] is not None
    assert report["inferred"]["status"] in {"stub", "signal", "absent"}


def test_detect_stub_user_hint(settings: Settings, tmp_path) -> None:
    import shutil


    ws_file = settings.workspace_path / "hint-test.wav"
    shutil.copy(settings.fixtures_path / "tone.wav", ws_file)
    store = AssetStore(settings)
    asset = store.register_workspace_file("hint-test.wav", user_hints={"generator": "suno"})
    runner = PipelineRunner(settings=settings, asset_store=store)
    audit, _ = runner.run("provenance-analysis@1", asset.asset_id)
    import json
    from pathlib import Path

    report = json.loads(Path(audit.report_path).read_text(encoding="utf-8"))
    assert report["inferred"]["status"] == "signal"
    signals = report["inferred"]["results"][0]["signals"]
    assert any(s["kind"] == "user_hint" for s in signals)


def test_detect_stub_plugin_direct() -> None:
    from pathlib import Path

    from audio_prov.models import TagResult
    from audio_prov.plugins.detect_stub import StubDetectPlugin

    plugin = StubDetectPlugin()
    result = plugin.detect(
        Path("/tmp/x.wav"),
        tags=TagResult(tags={"encoder": "Lavf61.1.100 (Suno export)"}),
    )
    assert result.status == "signal"
    assert result.signals[0]["kind"] == "tag_hint"


def test_batch_analyze_workspace(settings: Settings) -> None:
    import shutil

    from audio_prov.batch import batch_analyze_workspace

    for name in ("batch-a.wav", "batch-b.wav"):
        shutil.copy(settings.fixtures_path / "tone.wav", settings.workspace_path / name)
    store = AssetStore(settings)
    runner = PipelineRunner(settings=settings, asset_store=store)
    payload = batch_analyze_workspace(store, runner, glob_pattern="batch-*.wav")
    assert payload["count"] == 2
    assert len(payload["results"]) == 2
    asset_ids = {r["asset_id"] for r in payload["results"]}
    assert asset_ids == {"batch-a", "batch-b"}


def test_cli_check(settings: Settings) -> None:
    from audio_prov.cli import main

    assert main(["check", "--json"]) == 0


def test_broken_fixture_invalid(runner: PipelineRunner) -> None:
    results = runner.verify_asset("broken-sig")
    assert any(r["status"] == "invalid" for r in results)


def test_runner_shares_asset_store(settings: Settings, tmp_path) -> None:
    import shutil

    ws_file = settings.workspace_path / "shared-store.wav"
    shutil.copy(settings.fixtures_path / "tone.wav", ws_file)
    store = AssetStore(settings)
    runner = PipelineRunner(settings=settings, asset_store=store)
    asset = store.register_workspace_file("shared-store.wav")
    audit, summary = runner.run("provenance-analysis@1", asset.asset_id)
    assert summary["verified_status"] in {"valid", "invalid", "absent"}


def test_resolve_asset_by_filename(settings: Settings, tmp_path) -> None:
    import shutil

    ws_file = settings.workspace_path / "ByName.wav"
    shutil.copy(settings.fixtures_path / "tone.wav", ws_file)
    store = AssetStore(settings)
    asset = store.resolve_asset_ref("ByName.wav")
    assert asset.asset_id == "byname"
    assert Path(asset.path).name == "ByName.wav"


def test_asset_not_found_error(settings: Settings) -> None:
    from audio_prov.errors import AssetNotFoundError

    store = AssetStore(settings)
    with pytest.raises(AssetNotFoundError) as exc:
        store.get_asset("does-not-exist")
    assert exc.value.code == "asset_not_found"


def test_describe_pipeline(runner: PipelineRunner) -> None:
    desc = runner.describe_pipeline("provenance-analysis@1")
    assert desc["id"] == "provenance-analysis@1"
    assert len(desc["steps"]) >= 4
    assert desc["steps"][0]["plugin"] == "inspect.ffprobe"


def test_check_setup(settings: Settings) -> None:
    from audio_prov.errors import check_setup

    status = check_setup(settings)
    assert "ready" in status
    assert len(status["checks"]) == 3


def test_summary_notes_absent_credentials(runner: PipelineRunner) -> None:
    from audio_prov.audit import _render_summary
    from audio_prov.models import (
        InferredBlock,
        InspectResult,
        ProvenanceReport,
        StructuralBlock,
        VerifiedBlock,
        VerifyStatus,
    )

    report = ProvenanceReport(
        asset_id="tone-wav",
        content_hash="abc",
        pipeline_id="provenance-analysis@1",
        run_id="test-run",
        structural=StructuralBlock(
            inspect=InspectResult(content_hash="abc", format_profile="pcm", duration_sec=1.0)
        ),
        verified=VerifiedBlock(status=VerifyStatus.ABSENT, results=[]),
        inferred=InferredBlock(status="stub", results=[]),
    )
    summary = _render_summary(report)
    assert "does not indicate whether the audio is AI-generated" in summary
    assert "Inferred | stub" in summary
    assert "no tag/filename hints" in summary
