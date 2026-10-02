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
    pre.add_argument("--provider", choices=("mistral", "groq"), help="select provider explicitly (mistral or groq)")
    pre.add_argument("--allow-unresolved-manifest", action="store_true")

    run = commands.add_parser("reproduce", help="run reference + custom generation, evaluation, and report")
    run.add_argument("--config", default="configs/experiment.lock.yaml")
    run.add_argument("--provider", choices=("mistral", "groq"), help="select provider explicitly (mistral or groq)")
    run.add_argument("--run-id")
    run.add_argument("--allow-unresolved-manifest", action="store_true")
    run.add_argument("--dry-run-reference", action="store_true")

    evaluate = commands.add_parser("evaluate", help="run the pinned official evaluator for a saved prediction file")
    evaluate.add_argument("--config", default="configs/experiment.lock.yaml")
    evaluate.add_argument("--run-dir", required=True)
    evaluate.add_argument("--arm", choices=("reference", "custom"), required=True)

    audit = commands.add_parser("audit", help="rebuild summary tables from saved evaluation evidence")
    audit.add_argument(
        "--config",
        default="configs/experiment.lock.yaml",
        help="accepted for compatibility; audit uses the saved run manifest",
    )
    audit.add_argument("--run-dir", required=True)

    smoke = commands.add_parser("smoke", help="run the offline synthetic end-to-end smoke test")
    smoke.add_argument(
        "--output",
        default="results/smoke",
        help="new output directory (existing directories are left untouched)",
    )

    ext = commands.add_parser(
        "external-benchmark",
        help="benchmark external coding agents (Codex CLI and Antigravity CLI)",
    )
    ext.add_argument(
        "--agent",
        choices=("codex", "agy", "all"),
        default="all",
        help="select external coding agent to benchmark (codex, agy, or all)",
    )
    ext.add_argument(
        "--config",
        default="configs/external-agents.yaml",
        help="path to external agents benchmark configuration file",
    )
    ext.add_argument("--run-id", help="unique benchmark run directory identifier")
    ext.add_argument("--task", help="target single SWE-bench instance ID")
    ext.add_argument("--resume", action="store_true", help="resume an interrupted or incomplete run")
    ext.add_argument("--dry-run", action="store_true", help="validate environment and manifests without running agents")
    ext.add_argument("--smoke", action="store_true", help="run integration smoke test on disposable synthetic repository")
    ext.add_argument("--generation-only", action="store_true", help="run agent generation without official evaluation")
    ext.add_argument("--evaluate-only", action="store_true", help="run official evaluation on existing run directory")
    return parser


def main(argv: list[str] | None = None) -> int:
    load_env_file()
    args = _parser().parse_args(argv)
    try:
        if args.command == "smoke":
            output = run_smoke(args.output)
            print(json.dumps({"status": "passed", "run_dir": str(output)}, indent=2))
            return 0
        if args.command == "audit":
            summary = audit_run(args.run_dir)
            print(json.dumps(summary, indent=2))
            return 0
        if args.command == "external-benchmark":
            if getattr(args, "smoke", False):
                from .external_agents.smoke import run_external_smoke

                smoke_out = "results/external-smoke" if not args.run_id else f"results/{args.run_id}"
                smoke_report = run_external_smoke(smoke_out, agent_choice=args.agent)
                print(json.dumps(smoke_report, indent=2))
                return 0

            from .external_agents.config import ExternalAgentsConfig
            from .external_agents.runner import run_benchmark

            ext_cfg = ExternalAgentsConfig.load(args.config)
            out_dir = run_benchmark(
                ext_cfg,
                agent_choice=args.agent,
                run_id=args.run_id,
                resume=args.resume,
                dry_run_only=args.dry_run,
                generation_only=args.generation_only,
                evaluate_only=args.evaluate_only,
                target_task_id=args.task,
            )
            if not args.dry_run:
                print(json.dumps({"status": "completed", "run_dir": str(out_dir)}, indent=2))
            return 0
        config_path = args.config
        if getattr(args, "provider", None) == "groq" and config_path in {"configs/experiment.lock.yaml", "configs/experiment.mistral.yaml"}:
            config_path = "configs/experiment.groq.yaml"
        elif getattr(args, "provider", None) == "mistral" and config_path in {"configs/experiment.lock.yaml", "configs/experiment.groq.yaml"}:
            config_path = "configs/experiment.mistral.yaml"
        config = ExperimentConfig.load(config_path)
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
    except (ConfigError, OSError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2
