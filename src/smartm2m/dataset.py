"""Pinned SWE-bench dataset materialization with an explicit leakage boundary."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .config import ConfigError, ExperimentConfig

# These are the only dataset columns allowed into the generation/reference
# path.  The evaluator-only columns are intentionally absent.
SAFE_GENERATION_COLUMNS = (
    "instance_id",
    "repo",
    "base_commit",
    "problem_statement",
)


@dataclass(frozen=True)
class MaterializedDataset:
    path: str
    split: str
    count: int
    columns: tuple[str, ...]
    sha256: str
    evaluator_only: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def materialize_pinned_dataset(
    config: ExperimentConfig,
    destination: str | Path,
    *,
    evaluator_only: bool,
) -> MaterializedDataset:
    """Download one immutable revision and write a local parquet dataset.

    The generation materialization is deliberately projected before it is
    written.  The full row, including gold/evaluator fields, is materialized
    only after both prediction files have been sealed for official scoring.
    """
    if not config.dataset_name or not config.dataset_revision:
        raise ConfigError("dataset_name and immutable dataset_revision are required")
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise ConfigError("install requirements-evaluation.txt to materialize the pinned dataset") from exc

    try:
        dataset = load_dataset(
            config.dataset_name,
            revision=config.dataset_revision,
            split=config.reference.split,
        )
    except Exception as exc:
        raise ConfigError(
            f"could not load pinned dataset {config.dataset_name}@{config.dataset_revision}: {exc}"
        ) from exc

    required = set(SAFE_GENERATION_COLUMNS)
    missing = sorted(required - set(dataset.column_names))
    if missing:
        raise ConfigError(f"pinned dataset is missing generation columns: {', '.join(missing)}")
    selected = {task.instance_id for task in config.tasks}
    available = set(str(value) for value in dataset["instance_id"])
    missing_ids = sorted(selected - available)
    if missing_ids:
        raise ConfigError(f"pinned dataset is missing frozen task IDs: {', '.join(missing_ids)}")

    if evaluator_only:
        materialized = dataset
    else:
        materialized = dataset.select_columns(list(SAFE_GENERATION_COLUMNS))

    root = Path(destination).resolve()
    root.mkdir(parents=True, exist_ok=True)
    output = root / f"{config.reference.split}.parquet"
    try:
        materialized.to_parquet(str(output))
    except Exception as exc:
        raise ConfigError(f"could not write pinned local dataset {output}: {exc}") from exc
    return MaterializedDataset(
        path=str(root),
        split=config.reference.split,
        count=len(materialized),
        columns=tuple(materialized.column_names),
        sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        evaluator_only=evaluator_only,
    )
