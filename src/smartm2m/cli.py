"""Command-line entry points for the SMARTM2M Track 3 harness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import ConfigError, ExperimentConfig, load_env_file
from .evaluator import OfficialEvaluator
from .experiment import audit_run, preflight, reproduce
from .smoke import run_smoke


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smartm2m",
        description="Reproduce the SMARTM2M Track 3 reference/custom SWE-agent comparison.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    pre = commands.add_parser("preflight", help="validate pins, manifest shape, and local prerequisites")
    pre.add_argument("--config", default="configs/experiment.lock.yaml")
    pre.add_argument("--allow-unresolved-manifest", action="store_true")

    run = commands.add_parser("reproduce", help="run reference + custom generation, evaluation, and report")
    run.add_argument("--config", default="configs/experiment.lock.yaml")
    run.add_argument("--run-id")
    run.add_argument("--allow-unresolved-manifest", action="store_true")
    run.add_argument("--dry-run-reference", action="store_true")

    evaluate = commands.add_parser("evaluate", help="run the pinned official evaluator for a saved prediction file")
    evaluate.add_argument("--config", default="configs/experiment.lock.yaml")
    evaluate.add_argument("--run-dir", required=True)
    evaluate.add_argument("--arm", choices=("reference", "custom"), required=True)

    audit = commands.add_parser("audit", help="rebuild summary tables from saved evaluation evidence")
    audit.add_argument("--config", default="configs/experiment.lock.yaml")
    audit.add_argument("--run-dir", required=True)

    smoke = commands.add_parser("smoke", help="run the offline synthetic end-to-end smoke test")
    smoke.add_argument("--output", default="results/smoke")
    return parser


def main(argv: list[str] | None = None) -> int:
    load_env_file()
    args = _parser().parse_args(argv)
    try:
        if args.command == "smoke":
            output = run_smoke(args.output)
            print(json.dumps({"status": "passed", "run_dir": str(output)}, indent=2))
            return 0
        config = ExperimentConfig.load(args.config)
        if args.command == "preflight":
            report = preflight(config, allow_unresolved=args.allow_unresolved_manifest)
            print(json.dumps(report, indent=2))
            return 0 if report["ok"] else 2
        if args.command == "reproduce":
            run_dir = reproduce(
                config,
                run_id=args.run_id,
                allow_unresolved=args.allow_unresolved_manifest,
                dry_run_reference=args.dry_run_reference,
            )
            print(json.dumps({"run_dir": str(run_dir), "summary": json.loads((run_dir / "summary.json").read_text())}, indent=2))
            return 0
        if args.command == "evaluate":
            run_dir = Path(args.run_dir).resolve()
            prediction = run_dir / args.arm / "predictions.jsonl"
            dataset_path = run_dir / "dataset-evaluation"
            result = OfficialEvaluator(config).run(
                prediction,
                f"{run_dir.name}-{args.arm}-reeval",
                run_dir / "evaluation" / args.arm,
                dataset_name=str(dataset_path) if dataset_path.is_dir() else None,
            )
            print(json.dumps(result.as_dict(), indent=2))
            return 0 if result.status == "completed" else 2
        if args.command == "audit":
            summary = audit_run(args.run_dir, config)
            print(json.dumps(summary, indent=2))
            return 0
    except (ConfigError, OSError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2
