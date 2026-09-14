import json
import sys
from pathlib import Path

from smartm2m.config import ArmConfig, ExperimentConfig, ModelConfig, ReferenceConfig
from smartm2m.evaluator import OfficialEvaluator
from smartm2m.reporting import load_records


def _config(tmp_path: Path, command: str) -> ExperimentConfig:
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"tasks": []}\n', encoding="utf-8")
    config_path = tmp_path / "experiment.json"
    config_path.write_text('{}\n', encoding="utf-8")
    return ExperimentConfig(
        protocol_version="test",
        manifest_path=manifest,
        expected_count=0,
        tasks=(),
        model=ModelConfig(),
        reference=ReferenceConfig(split="dev"),
        custom=ArmConfig(),
        baseline=ArmConfig(),
        results_root=tmp_path,
        official_evaluator_command=command,
        config_path=config_path,
    )


def test_official_evaluator_keeps_cwd_relative_reports_in_arm_directory(tmp_path: Path):
    script = tmp_path / "fake_evaluator.py"
    script.write_text(
        "from pathlib import Path\n"
        "import json\n"
        "Path('cwd.marker').write_text(str(Path.cwd()))\n"
        "report = Path('logs/evaluation/fake')\n"
        "report.mkdir(parents=True)\n"
        "(report / 'report.json').write_text(json.dumps({'synthetic__one': {'resolved': True}}))\n",
        encoding="utf-8",
    )
    config = _config(tmp_path, f"{sys.executable} {script}")
    predictions = tmp_path / "predictions.jsonl"
    predictions.write_text("{}\n", encoding="utf-8")
    output = tmp_path / "evaluation" / "custom"

    result = OfficialEvaluator(config).run(predictions, "fake-run", output)

    assert result.status == "completed"
    assert (output / "cwd.marker").is_file()
    records = load_records(output)
    assert records["synthetic__one"]["resolved"] is True
    saved = json.loads((output / "evaluation-run.json").read_text(encoding="utf-8"))
    assert saved["working_directory"] == str(output.resolve())


def test_official_evaluator_accepts_materialized_dataset_override():
    root = Path(__file__).parents[1]
    evaluator = OfficialEvaluator(ExperimentConfig.load(root / "configs/experiment.lock.yaml"))

    command = evaluator.command(
        Path("/tmp/predictions.jsonl"),
        "audit",
        dataset_name="/tmp/pinned-evaluator-dataset",
    )

    assert command[command.index("--dataset_name") + 1] == "/tmp/pinned-evaluator-dataset"
