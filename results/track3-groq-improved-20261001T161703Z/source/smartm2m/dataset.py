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

EVALUATOR_COLUMNS = {"image", "eval_script", "log_parser", "eval_type"}


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
        rows = list(dataset)
        needs_enrichment = not EVALUATOR_COLUMNS.issubset(set(dataset.column_names)) or any(
            not str(row.get(column) or "").strip()
            for row in rows
            for column in EVALUATOR_COLUMNS
        )
        if needs_enrichment:
            try:
                metadata_ds = load_dataset(
                    config.evaluator_metadata_dataset,
                    revision=config.evaluator_metadata_revision,
                    split=config.reference.split,
                )
            except Exception as exc:
                raise ConfigError(
                    "could not load pinned evaluator metadata "
                    f"{config.evaluator_metadata_dataset}@{config.evaluator_metadata_revision}: {exc}"
                ) from exc

            required_metadata_columns = EVALUATOR_COLUMNS | {"instance_id", "repo", "base_commit"}
            missing_metadata_columns = sorted(required_metadata_columns - set(metadata_ds.column_names))
            if missing_metadata_columns:
                raise ConfigError(
                    "pinned evaluator metadata is missing columns: "
                    + ", ".join(missing_metadata_columns)
                )

            verified_map = {str(row["instance_id"]): row for row in metadata_ds}
            missing_metadata_ids: list[str] = []
            mismatched_metadata_ids: list[str] = []
            incomplete_metadata_ids: list[str] = []
            augmented_rows = []
            for row in rows:
                instance_id = str(row["instance_id"])
                verified_row = verified_map.get(instance_id)
                if verified_row is None:
                    missing_metadata_ids.append(instance_id)
                    continue
                if (
                    str(verified_row.get("repo", "")) != str(row.get("repo", ""))
                    or str(verified_row.get("base_commit", "")) != str(row.get("base_commit", ""))
                ):
                    mismatched_metadata_ids.append(instance_id)
                    continue
                row_dict = dict(row)
                for column in EVALUATOR_COLUMNS:
                    if not str(row_dict.get(column) or "").strip():
                        row_dict[column] = verified_row.get(column, "")
                    if not str(row_dict.get(column) or "").strip():
                        incomplete_metadata_ids.append(instance_id)
                augmented_rows.append(row_dict)

            if missing_metadata_ids:
                raise ConfigError(
                    "pinned evaluator metadata is missing task IDs: "
                    + ", ".join(sorted(missing_metadata_ids)[:10])
                )
            if mismatched_metadata_ids:
                raise ConfigError(
                    "pinned evaluator metadata repo/base commit does not match task IDs: "
                    + ", ".join(sorted(mismatched_metadata_ids)[:10])
                )
            if incomplete_metadata_ids:
                raise ConfigError(
                    "pinned evaluator metadata has empty required fields for task IDs: "
                    + ", ".join(sorted(set(incomplete_metadata_ids))[:10])
                )

            try:
                from datasets import Dataset

                materialized = Dataset.from_list(augmented_rows)
            except Exception as exc:
                raise ConfigError(f"could not combine pinned evaluator metadata: {exc}") from exc
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
