from __future__ import annotations

import argparse
import json
import sys

from audio_prov.audit import load_run
from audio_prov.config import get_settings
from audio_prov.pipeline import PipelineRunner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audio provenance CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Run a provenance pipeline")
    run_parser.add_argument("pipeline_id")
    run_parser.add_argument("--asset", required=True, dest="asset_id")
    run_parser.add_argument("--preset", default=None)
    run_parser.add_argument("--json", action="store_true")

    verify_parser = sub.add_parser("verify", help="Verify credentials for an asset")
    verify_parser.add_argument("--asset", required=True, dest="asset_id")
    verify_parser.add_argument("--json", action="store_true")

    get_parser = sub.add_parser("get-run", help="Load a prior run audit")
    get_parser.add_argument("run_id")
    get_parser.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    settings = get_settings()
    runner = PipelineRunner(settings=settings)

    if args.command == "run":
        options = {}
        if args.preset:
            options["preset"] = args.preset
        audit, summary = runner.run(args.pipeline_id, args.asset_id, options=options)
        payload = {"audit": audit.model_dump(), "summary": summary}
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"Run {summary['run_id']} complete")
            print(f"Verified: {summary['verified_status']}")
            print(f"Report: {summary['report_path']}")
        return 0

    if args.command == "verify":
        results = runner.verify_asset(args.asset_id)
        if args.json:
            payload = {"results": results, "verified": merge_verified_dump(results)}
            print(json.dumps(payload, indent=2))
        else:
            for item in results:
                print(f"{item['plugin_id']}: {item['status']}")
        return 0

    if args.command == "get-run":
        payload = load_run(settings, args.run_id)
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(json.dumps(payload["audit"], indent=2))
        return 0

    return 1


def merge_verified_dump(results: list[dict]) -> str:
    if any(r.get("status") == "invalid" for r in results):
        return "invalid"
    if any(r.get("status") == "valid" for r in results):
        return "valid"
    return "absent"


if __name__ == "__main__":
    sys.exit(main())
