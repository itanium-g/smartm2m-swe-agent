import sys
import types
from pathlib import Path

from smartm2m.config import ExperimentConfig
from smartm2m.dataset import SAFE_GENERATION_COLUMNS, materialize_pinned_dataset


class _FakeDataset:
    def __init__(self, columns):
        self.column_names = list(columns)

    def __getitem__(self, name):
        if name == "instance_id":
            return ["synthetic__one"]
        raise KeyError(name)

    def select_columns(self, columns):
        return _FakeDataset(columns)

    def __len__(self):
        return 1

    def to_parquet(self, path):
        Path(path).write_text("\n".join(self.column_names), encoding="utf-8")


def test_generation_dataset_projection_excludes_evaluator_columns(monkeypatch, tmp_path: Path):
    config = ExperimentConfig.load(Path(__file__).parents[1] / "configs/experiment.lock.yaml")
    config = config.__class__(
        **{
            **config.__dict__,
            "protocol_version": "test",
            "tasks": (config.tasks[0].__class__(
                "synthetic__one",
                "Fix it.",
                repo="owner/repo",
                base_commit="abc",
            ),),
            "expected_count": 1,
        }
    )
    full_columns = [
        *SAFE_GENERATION_COLUMNS,
        "patch",
        "test_patch",
        "hints_text",
        "FAIL_TO_PASS",
        "PASS_TO_PASS",
    ]
    monkeypatch.setitem(
        sys.modules,
        "datasets",
        types.SimpleNamespace(
            load_dataset=lambda *args, **kwargs: _FakeDataset(full_columns),
        ),
    )

    result = materialize_pinned_dataset(config, tmp_path / "safe", evaluator_only=False)

    assert result.columns == SAFE_GENERATION_COLUMNS
    written = (tmp_path / "safe" / "test.parquet").read_text(encoding="utf-8").splitlines()
    assert written == list(SAFE_GENERATION_COLUMNS)
    assert not set(written).intersection({"patch", "test_patch", "hints_text", "FAIL_TO_PASS", "PASS_TO_PASS"})
