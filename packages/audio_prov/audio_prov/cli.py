from __future__ import annotations

import argparse
import json
import sys

from audio_prov.assets import AssetStore
from audio_prov.audit import load_batch, load_run
from audio_prov.batch import batch_analyze_workspace, cancel_batch_job, start_batch_job
from audio_prov.config import get_settings
from audio_prov.errors import check_setup
from audio_prov.pipeline import PipelineRunner
from audio_prov.plugins.verify_demo import sign_demo_manifest
from audio_prov.registry import default_registry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audio provenance CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Run a provenance pipeline")
    run_parser.add_argument("pipeline_id")
    run_parser.add_argument(
        "--asset",
        required=True,
        dest="asset_ref",
        help="asset_id, fixture id, or workspace filename",
    )
    run_parser.add_argument("--preset", default=None)
    run_parser.add_argument("--json", action="store_true")

    batch_parser = sub.add_parser("batch", help="Analyze all audio files in workspace/")
    batch_parser.add_argument(
        "--pipeline",
        default="provenance-analysis@1",
        dest="pipeline_id",
    )
    batch_parser.add_argument("--preset", default=None)
    batch_parser.add_argument("--glob", default=None, dest="glob_pattern")
    batch_parser.add_argument(
        "--async",
        action="store_true",
        dest="async_mode",
        help="Start background batch job and return batch_id immediately",
    )
    batch_parser.add_argument("--json", action="store_true")

    batch_status_parser = sub.add_parser("batch-status", help="Poll an async batch job")
    batch_status_parser.add_argument("batch_id")
    batch_status_parser.add_argument("--json", action="store_true")

    batch_cancel_parser = sub.add_parser("batch-cancel", help="Cancel a running async batch")
    batch_cancel_parser.add_argument("batch_id")
    batch_cancel_parser.add_argument("--json", action="store_true")

    verify_parser = sub.add_parser("verify", help="Verify credentials for an asset")
    verify_parser.add_argument("--asset", required=True, dest="asset_ref")
    verify_parser.add_argument("--json", action="store_true")

    list_parser = sub.add_parser("list-workspace", help="List workspace audio files")
    list_parser.add_argument("--json", action="store_true")

    check_parser = sub.add_parser("check", help="Check ffmpeg/ffprobe prerequisites")
    check_parser.add_argument("--json", action="store_true")

    sign_parser = sub.add_parser(
        "sign-demo",
        help="Write demo sidecar manifest for a workspace file (dev keys only)",
    )
    sign_parser.add_argument("filename", help="Workspace filename")
    sign_parser.add_argument(
        "--claims",
        default='{"synthetic": true}',
        help="JSON claims object",
    )
    sign_parser.add_argument("--json", action="store_true")

    sign_c2pa_parser = sub.add_parser(
        "sign-c2pa",
        help="Embed C2PA manifest in a workspace file (dev cert by default)",
    )
    sign_c2pa_parser.add_argument("filename", help="Workspace filename")
    sign_c2pa_parser.add_argument(
        "--manifest",
        default=None,
        help="Manifest JSON path (default: schemas/c2pa/dev-manifest.json)",
    )
    sign_c2pa_parser.add_argument(
        "--output",
        default=None,
        help="Output path (default: overwrite source in place)",
    )
    sign_c2pa_parser.add_argument("--json", action="store_true")

    get_parser = sub.add_parser("get-run", help="Load a prior run audit")
    get_parser.add_argument("run_id")
    get_parser.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    settings = get_settings()
    store = AssetStore(settings)
    runner = PipelineRunner(settings=settings, asset_store=store)
    registry = default_registry(settings)

    if args.command == "check":
        payload = check_setup(settings)
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            for item in payload["checks"]:
                mark = "ok" if item["ok"] else "MISSING"
                req = "required" if item["required"] else "optional"
                print(f"{item['tool']}: {mark} ({req})")
            print(f"ready: {payload['ready']}")
        return 0 if payload["ready"] else 1

    if args.command == "list-workspace":
        payload = store.list_workspace_files()
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            for item in payload:
                print(f"{item['name']}\t{item['size']} bytes")
        return 0

    if args.command == "sign-demo":
        path = store.resolve_path(store.resolve_asset_ref(args.filename))
        claims = json.loads(args.claims)
        sign_demo_manifest(path, claims)
        payload = {"filename": args.filename, "path": str(path), "claims": claims}
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"Signed demo sidecar for {args.filename}")
        return 0

    if args.command == "sign-c2pa":
        from pathlib import Path

        from audio_prov.errors import SignError

        asset = store.resolve_asset_ref(args.filename)
        path = store.resolve_path(asset)
        manifest = Path(args.manifest) if args.manifest else None
        output = Path(args.output) if args.output else None
        plugin = registry.get_sign("sign.c2pa")
        try:
            payload = plugin.sign(path, manifest_path=manifest, output_path=output)
        except SignError as exc:
            if args.json:
                print(json.dumps(exc.as_dict(), indent=2))
            else:
                print(str(exc), file=sys.stderr)
            return 1
        payload["asset_id"] = asset.asset_id
        payload["filename"] = args.filename
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            target = payload["output_path"]
            print(f"Embedded C2PA manifest in {target} ({payload['signing_note']})")
        return 0

    if args.command == "batch":
        if args.async_mode:
            payload = start_batch_job(
                store,
                runner,
                pipeline_id=args.pipeline_id,
                preset=args.preset,
                glob_pattern=args.glob_pattern,
            )
        else:
            payload = batch_analyze_workspace(
                store,
                runner,
                pipeline_id=args.pipeline_id,
                preset=args.preset,
                glob_pattern=args.glob_pattern,
            )
        if args.json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            if payload.get("async"):
                print(f"Batch {payload['batch_id']} started ({payload['status']})")
                print(f"Poll: audio-prov batch-status {payload['batch_id']}")
            else:
                print(f"Analyzed {payload['count']} file(s) with {payload['pipeline_id']}")
            print(f"Batch summary: {payload['batch_summary_path']}")
            for item in payload["results"]:
                s = item["summary"]
                print(
                    f"  {item['filename']} ({item['asset_id']}): "
                    f"verified={s['verified_status']} run={item['run_id']}"
                )
        return 0

    if args.command == "batch-status":
        from audio_prov.batch import format_batch_status
        from audio_prov.errors import BatchNotFoundError

        try:
            payload = load_batch(settings, args.batch_id)
        except BatchNotFoundError as exc:
            if args.json:
                print(json.dumps(exc.as_dict(), indent=2))
            else:
                print(str(exc), file=sys.stderr)
            return 1
        response = format_batch_status(payload, settings)
        if args.json:
            print(json.dumps(response, indent=2, default=str))
        else:
            print(
                f"Batch {response['batch_id']}: {response['status']} "
                f"({response['completed']}/{response['total']})"
            )
            if response.get("error"):
                print(f"Error: {response['error']}")
        return 0

    if args.command == "batch-cancel":
        from audio_prov.errors import BatchNotFoundError

        try:
            payload = cancel_batch_job(settings, args.batch_id)
        except BatchNotFoundError as exc:
            if args.json:
                print(json.dumps(exc.as_dict(), indent=2))
            else:
                print(str(exc), file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"Batch {payload['batch_id']}: {payload['status']}")
        return 0

    if args.command == "run":
        asset = store.resolve_asset_ref(args.asset_ref)
        options = {}
        if args.preset:
            options["preset"] = args.preset
        audit, summary = runner.run(args.pipeline_id, asset.asset_id, options=options)
        payload = {"audit": audit.model_dump(), "summary": summary}
        if args.json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(f"Run {summary['run_id']} complete")
            print(f"Verified: {summary['verified_status']}")
            print(f"Report: {summary['report_path']}")
        return 0

    if args.command == "verify":
        asset = store.resolve_asset_ref(args.asset_ref)
        results = runner.verify_asset(asset.asset_id)
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
