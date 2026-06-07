from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from audio_prov.config import Settings
from audio_prov.errors import SignError
from audio_prov.plugins.verify_c2pa import _resolve_tool

_DEV_SIGNING_NOTE = "c2pa-development-certificate"
_OPERATOR_SIGNING_NOTE = "operator-provided-certificate"


def default_manifest_path(settings: Settings) -> Path:
    return settings.schemas_path / "c2pa" / "dev-manifest.json"


@dataclass
class PreparedManifest:
    path: Path
    signing_note: str
    cleanup: bool = False

    def dispose(self) -> None:
        if self.cleanup and self.path.is_file():
            self.path.unlink(missing_ok=True)


def prepare_sign_manifest(
    settings: Settings,
    manifest_path: Path | None = None,
) -> PreparedManifest:
    if manifest_path is not None:
        if not manifest_path.is_file():
            raise SignError(
                f"manifest not found: {manifest_path}",
                hint="Provide a valid C2PA manifest definition JSON file.",
            )
        note = (
            _OPERATOR_SIGNING_NOTE
            if _uses_operator_credentials(manifest_path)
            else _DEV_SIGNING_NOTE
        )
        return PreparedManifest(path=manifest_path, signing_note=note)

    if settings.c2pa_manifest_path:
        configured = Path(settings.c2pa_manifest_path)
        if not configured.is_file():
            raise SignError(
                f"manifest not found: {configured}",
                hint="Set AUDIO_PROV_C2PA_MANIFEST to a valid manifest JSON path.",
            )
        return PreparedManifest(
            path=configured,
            signing_note=_OPERATOR_SIGNING_NOTE,
        )

    if settings.c2pa_private_key and settings.c2pa_sign_cert:
        return _build_operator_manifest(settings)

    dev_path = default_manifest_path(settings)
    if not dev_path.is_file():
        raise SignError(
            f"manifest not found: {dev_path}",
            hint="Add schemas/c2pa/dev-manifest.json or set AUDIO_PROV_C2PA_MANIFEST.",
        )
    return PreparedManifest(path=dev_path, signing_note=_DEV_SIGNING_NOTE)


def _uses_operator_credentials(manifest_path: Path) -> bool:
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return bool(data.get("private_key") or data.get("sign_cert"))


def _build_operator_manifest(settings: Settings) -> PreparedManifest:
    private_key = Path(settings.c2pa_private_key or "")
    sign_cert = Path(settings.c2pa_sign_cert or "")
    if not private_key.is_file():
        raise SignError(
            f"private key not found: {private_key}",
            hint="Set AUDIO_PROV_C2PA_PRIVATE_KEY to your signing key path.",
        )
    if not sign_cert.is_file():
        raise SignError(
            f"signing certificate not found: {sign_cert}",
            hint="Set AUDIO_PROV_C2PA_SIGN_CERT to your certificate PEM path.",
        )

    base = json.loads(default_manifest_path(settings).read_text(encoding="utf-8"))
    base["alg"] = settings.c2pa_sign_alg
    base["private_key"] = str(private_key.resolve())
    base["sign_cert"] = str(sign_cert.resolve())
    if settings.c2pa_ta_url:
        base["ta_url"] = settings.c2pa_ta_url

    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix="audio-prov-c2pa-",
        delete=False,
        encoding="utf-8",
    )
    json.dump(base, tmp, indent=2)
    tmp.close()
    return PreparedManifest(
        path=Path(tmp.name),
        signing_note=_OPERATOR_SIGNING_NOTE,
        cleanup=True,
    )


def sign_c2pa_embed(
    path: Path,
    settings: Settings,
    *,
    manifest_path: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, str]:
    """Embed a C2PA manifest in an audio file using c2patool."""
    tool = _resolve_tool(settings.c2patool_path)
    if tool is None:
        raise SignError(
            "c2patool not installed",
            hint=(
                "Install c2patool (brew install c2patool) or set "
                "AUDIO_PROV_C2PATOOL to the binary path"
            ),
        )

    prepared = prepare_sign_manifest(settings, manifest_path)
    try:
        manifest = prepared.path
        output = output_path or path
        if output.suffix.lower() != path.suffix.lower():
            raise SignError(
                "output extension must match source file",
                hint="c2patool does not convert between formats",
            )

        try:
            proc = subprocess.run(
                [tool, str(path), "-m", str(manifest), "-o", str(output), "-f"],
                capture_output=True,
                text=True,
                timeout=180,
            )
        except subprocess.TimeoutExpired as exc:
            raise SignError("c2patool timed out") from exc

        output_text = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0 or not output.is_file():
            raise SignError(
                "c2patool signing failed",
                hint=output_text.strip()[:500] or None,
            )

        return {
            "input_path": str(path),
            "output_path": str(output),
            "manifest_path": str(manifest),
            "signing_note": prepared.signing_note,
            "in_place": str(output.resolve()) == str(path.resolve()),
        }
    finally:
        prepared.dispose()


class C2paSignPlugin:
    id = "c2pa"
    version = "0.1.0"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def sign(
        self,
        path: Path,
        *,
        manifest_path: Path | None = None,
        output_path: Path | None = None,
    ) -> dict[str, str]:
        return sign_c2pa_embed(
            path,
            self.settings,
            manifest_path=manifest_path,
            output_path=output_path,
        )
