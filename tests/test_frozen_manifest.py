import hashlib
import json
import random
from pathlib import Path

from smartm2m.config import ExperimentConfig
from smartm2m.task import generation_payload


def test_production_manifest_is_frozen_and_matches_selection():
    root = Path(__file__).parents[1]
    config = ExperimentConfig.load(root / "configs/experiment.lock.yaml")
    assert len(config.tasks) == 8
    assert config.expected_count == 8
    assert config.dataset_revision == "b316c349947c29963fce3f4a65967c9807a4b673"
    selection = json.loads((root / "tasks/evaluation.selection.json").read_text(encoding="utf-8"))
    pool = [line.strip() for line in (root / "tasks/verified_mini_pool.txt").read_text().splitlines() if line.strip()]
    expected = random.Random(selection["seed"]).sample(sorted(pool), selection["count"])
    actual = [task.instance_id for task in config.tasks]
    assert actual == expected == selection["selected_ids"]
    assert hashlib.sha256("\n".join(actual).encode()).hexdigest() == selection["selected_ids_sha256"]
    assert config.validate_manifest() == []


def test_frozen_generation_payloads_have_no_hidden_keys():
    root = Path(__file__).parents[1]
    config = ExperimentConfig.load(root / "configs/experiment.lock.yaml")
    hidden = {"patch", "test_patch", "hints_text", "fail_to_pass", "pass_to_pass", "FAIL_TO_PASS", "PASS_TO_PASS"}
    for task in config.tasks:
        payload = generation_payload(task)
        assert not hidden.intersection(payload)
        assert payload["repo_url"].startswith("https://github.com/")
