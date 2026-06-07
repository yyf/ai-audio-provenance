from __future__ import annotations

from pathlib import Path

from audio_prov.models import DetectResult, TagResult


class WatermarkStubDetectPlugin:
    """Placeholder watermark extractor — vendor-specific decoders not implemented."""

    id = "watermark"
    version = "0.1.0"

    def detect(
        self,
        path: Path,
        tags: TagResult | None = None,
        user_hints: dict | None = None,
    ) -> DetectResult:
        return DetectResult(
            plugin_id="detect.watermark",
            plugin_version=self.version,
            status="absent",
            signals=[],
            details={
                "message": (
                    "Vendor-specific audio watermark extraction is not implemented. "
                    "Register a DetectPlugin for your watermark provider."
                ),
                "path": str(path),
            },
        )
