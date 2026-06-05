from __future__ import annotations

from pathlib import Path

from audio_prov.models import DetectResult, TagResult

# Substrings in tag values or filenames that may indicate a generator (hint only, not proof).
_HINT_PATTERNS: tuple[tuple[str, str], ...] = (
    ("suno", "Possible Suno export"),
    ("udio", "Possible Udio export"),
    ("elevenlabs", "Possible ElevenLabs TTS"),
    ("openai", "Possible OpenAI TTS"),
    ("lavf", "FFmpeg/libav encoding (common in re-exports)"),
)


def _append_hint(
    signals: list[dict[str, str]],
    kind: str,
    source: str,
    value: str,
    patterns: tuple[tuple[str, str], ...] = _HINT_PATTERNS,
) -> None:
    lowered = value.lower()
    for pattern, label in patterns:
        if pattern in lowered:
            signals.append(
                {
                    "kind": kind,
                    "source": source,
                    "value": value,
                    "note": f"{label} (not verified)",
                }
            )
            break


class StubDetectPlugin:
    """Placeholder detector — tag hints and user hints only, never forensic proof."""

    id = "stub"
    version = "0.1.0"

    def detect(
        self,
        path: Path,
        tags: TagResult | None = None,
        user_hints: dict | None = None,
    ) -> DetectResult:
        signals: list[dict[str, str]] = []
        tag_map = tags.tags if tags else {}

        for key, value in tag_map.items():
            _append_hint(signals, "tag_hint", key, value)

        _append_hint(signals, "filename_hint", "filename", path.name)

        hints = user_hints or {}
        if generator := hints.get("generator"):
            signals.append(
                {
                    "kind": "user_hint",
                    "source": "user_hints.generator",
                    "value": str(generator),
                    "note": "Operator-declared generator (not verified)",
                }
            )

        status = "signal" if signals else "stub"
        return DetectResult(
            plugin_id="detect.stub",
            plugin_version=self.version,
            status=status,
            signals=signals,
            details={
                "message": (
                    "No external AI detector configured. "
                    "Signals above are tag/hint based only."
                ),
                "path": str(path),
            },
        )
