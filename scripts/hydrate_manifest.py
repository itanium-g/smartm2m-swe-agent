#!/usr/bin/env python3
"""Hydrate the frozen IDs into a generation-safe task manifest.

Only issue text, repository identity, base commit, and runtime metadata are
copied. Gold patches, test patches, hints, and evaluator test labels are
explicitly rejected and never written to the output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

HIDDEN = {"patch", "test_patch", "hints_text", "fail_to_pass", "pass_to_pass", "FAIL_TO_PASS", "PASS_TO_PASS"}


def _image(instance_id: str) -> str:
    docker_id = instance_id.replace("__", "_1776_").lower()
    return f"docker.io/swebench/sweb.eval.x86_64.{docker_id}:latest"


def _selection_hash(ids: list[str]) -> str:
    return hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()


def _safe_task(row: dict[str, Any]) -> dict[str, Any]:
    instance_id = str(row["instance_id"])
    repo = str(row["repo"])
    if "/" not in repo:
        raise ValueError(f"{instance_id}: dataset repo is not owner/name: {repo}")
    if repo == "django/django":
        tests = ["python tests/runtests.py --verbosity 1"]
        profile = "django-runtests"
    elif repo == "sphinx-doc/sphinx":
        tests = ["python -m pytest -q"]
        profile = "pytest"
    else:
        raise ValueError(f"{instance_id}: no safe repository-native test profile for {repo}")
    task = {
        "instance_id": instance_id,
        "problem_statement": str(row["problem_statement"]),
        "repo": repo,
        "base_commit": str(row["base_commit"]),
        "repo_url": f"https://github.com/{repo}.git",
        "split": "test",
        "image": str(row.get("image_name") or row.get("docker_image") or _image(instance_id)),
        "test_commands": tests,
        "setup_commands": [],
        "test_profile": profile,
    }
    for key in task:
        if key in HIDDEN or key.lower() in {item.lower() for item in HIDDEN}:
            raise ValueError(f"safe task unexpectedly contains evaluator field: {key}")
    return task


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="MariusHobbhahn/swe-bench-verified-mini")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--selection", type=Path, default=Path("tasks/evaluation.selection.json"))
    parser.add_argument("--output", type=Path, default=Path("tasks/evaluation.json"))
    args = parser.parse_args()
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    if selection.get("dataset_name") != args.dataset or selection.get("dataset_revision") != args.revision:
        raise SystemExit("selection metadata does not match --dataset/--revision")
    selected_ids = [str(value) for value in selection.get("selected_ids", [])]
    if selection.get("selected_ids_sha256") != _selection_hash(selected_ids):
        raise SystemExit("selection fingerprint does not match selected_ids")

    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise SystemExit("install requirements-evaluation.txt before hydrating the dataset") from exc
    dataset = load_dataset(args.dataset, revision=args.revision, split=str(selection.get("split", "test")))
    rows = {str(row["instance_id"]): dict(row) for row in dataset}
    missing = [instance_id for instance_id in selected_ids if instance_id not in rows]
    if missing:
        raise SystemExit(f"selected IDs are missing from the pinned dataset: {missing}")
    tasks = [_safe_task(rows[instance_id]) for instance_id in selected_ids]
    payload = {
        "status": "frozen",
        "source": {
            "dataset_name": args.dataset,
            "dataset_revision": args.revision,
            "split": selection.get("split", "test"),
            "selection_file": str(args.selection.as_posix()),
            "selection_algorithm": selection.get("algorithm"),
            "seed": selection.get("seed"),
            "selected_ids_sha256": selection["selected_ids_sha256"],
        },
        "expected_count": len(tasks),
        "tasks": tasks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "count": len(tasks), "ids": selected_ids}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
