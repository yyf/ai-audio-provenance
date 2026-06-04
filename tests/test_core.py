import pytest
from pathlib import Path

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
