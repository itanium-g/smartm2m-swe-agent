import json
import subprocess
import sys
from pathlib import Path

from smartm2m.config import ExperimentConfig
from smartm2m.experiment import reproduce


def _repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "experiment@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "experiment"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    return repo, base


def test_reproduce_runs_both_subprocess_boundaries_and_audits_reports(tmp_path: Path):
    repo, base = _repo(tmp_path)
    reference_script = tmp_path / "reference.py"
    reference_script.write_text(
        "import argparse, json\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--output', required=True)\n"
        "args = parser.parse_args()\n"
        "from pathlib import Path\n"
        "Path(args.output, 'preds.json').write_text(json.dumps({'synthetic__one': {'model_patch': ''}}))\n",
        encoding="utf-8",
    )
    evaluator_script = tmp_path / "evaluator.py"
    evaluator_script.write_text(
        "import argparse, json\n"
        "from pathlib import Path\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--predictions', required=True)\n"
        "parser.add_argument('--run-id', required=True)\n"
        "parser.add_argument('--split', required=True)\n"
        "args = parser.parse_args()\n"
        "row = json.loads(Path(args.predictions).read_text().splitlines()[0])\n"
        "target = Path('logs/evaluation') / args.run_id / 'fake' / row['instance_id']\n"
        "target.mkdir(parents=True)\n"
        "(target / 'report.json').write_text(json.dumps({row['instance_id']: {'resolved': bool(row['model_patch'])}}))\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "tasks": [{
            "instance_id": "synthetic__one",
            "problem_statement": "Make VALUE equal to two.",
            "repo_path": str(repo),
            "base_commit": base,
            "test_commands": ["python -c \"assert True\""],
        }],
    }), encoding="utf-8")
    config_path = tmp_path / "experiment.json"
    config_path.write_text(json.dumps({
        "protocol_version": "test",
        "manifest": {"path": "manifest.json", "expected_count": 1},
        "model": {"api_key_env": "SMARTM2M_TEST_MISSING_KEY"},
        "reference": {
            "executable": sys.executable,
            "command_template": f"{sys.executable} {reference_script} --output {{output}}",
        },
        "baseline": {"wall_time_seconds": 30},
        "custom": {"wall_time_seconds": 30},
        "official_evaluator_command": (
            f"{sys.executable} {evaluator_script} --predictions {{predictions}} "
            "--run-id {run_id} --split {split}"
        ),
        "results_root": "results",
    }), encoding="utf-8")

    run_dir = reproduce(ExperimentConfig.load(config_path), run_id="integration")

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["expected_count"] == 1
    assert summary["reference_resolved"] == 0
    assert summary["custom_resolved"] == 0
    assert (run_dir / "reference" / "predictions.raw.json").is_file()
    assert (run_dir / "evaluation" / "reference" / "logs" / "evaluation").is_dir()
    assert (run_dir / "evaluation" / "custom" / "logs" / "evaluation").is_dir()
