from __future__ import annotations

import base64
import json
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from audio_prov.models import VerifyResult, VerifyStatus
from audio_prov.util import sha256_file

# Development-only keypair for fixture manifests. Do not use in production.
_DEMO_PUBLIC_KEY_B64 = "uyD7FmSsn32adOAsjhPIWpIeibfdA3VwjDsmNfboQls="
_DEMO_PRIVATE_KEY_B64 = "mKeuQCFPICw+NIJsssOyhMHl9203jSrkzsTEpDCEx+0="
_DEMO_SIGNING_NOTE = "demo-development-key"


def manifest_paths(path: Path) -> tuple[Path, Path]:
    return (
        path.with_suffix(path.suffix + ".manifest.json"),
        path.with_suffix(path.suffix + ".manifest.sig"),
    )


def build_manifest_payload(path: Path, claims: dict) -> dict:
    return {
        "manifest_version": "demo-1",
        "content_hash": sha256_file(path),
        "claims": claims,
        "issuer": "audio-prov-demo",
    }


class DemoVerifyPlugin:
    id = "demo"
    version = "0.1.0"

    def verify(self, path: Path) -> VerifyResult:
        manifest_path, sig_path = manifest_paths(path)
        if not manifest_path.exists() or not sig_path.exists():
            return VerifyResult(
                plugin_id="verify.demo",
                plugin_version=self.version,
                status=VerifyStatus.ABSENT,
                details={"reason": "no_sidecar_manifest"},
            )

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            signature = base64.b64decode(sig_path.read_text(encoding="utf-8").strip())
            public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(_DEMO_PUBLIC_KEY_B64))
            canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
            public_key.verify(signature, canonical)
        except (InvalidSignature, json.JSONDecodeError, ValueError) as exc:
            return VerifyResult(
                plugin_id="verify.demo",
                plugin_version=self.version,
                status=VerifyStatus.INVALID,
                details={"reason": "signature_or_manifest_invalid", "error": str(exc)},
            )

        expected_hash = manifest.get("content_hash")
        actual_hash = sha256_file(path)
        if expected_hash != actual_hash:
            return VerifyResult(
                plugin_id="verify.demo",
                plugin_version=self.version,
                status=VerifyStatus.INVALID,
                details={
                    "reason": "content_hash_mismatch",
                    "expected": expected_hash,
                    "actual": actual_hash,
                },
            )

        return VerifyResult(
            plugin_id="verify.demo",
            plugin_version=self.version,
            status=VerifyStatus.VALID,
            details={
                "issuer": manifest.get("issuer"),
                "claims": manifest.get("claims", {}),
                "signing_note": _DEMO_SIGNING_NOTE,
            },
        )


def sign_demo_manifest(path: Path, claims: dict, private_key_b64: str | None = None) -> None:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key_b64 = private_key_b64 or _DEMO_PRIVATE_KEY_B64
    manifest = build_manifest_payload(path, claims)
    manifest_path, sig_path = manifest_paths(path)
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    private_key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(key_b64))
    signature = private_key.sign(canonical)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    sig_path.write_text(base64.b64encode(signature).decode("ascii"), encoding="utf-8")
