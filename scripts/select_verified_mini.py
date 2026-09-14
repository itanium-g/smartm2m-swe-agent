#!/usr/bin/env python3
"""Freeze a deterministic sample from the pinned Verified Mini pool.

The script deliberately records IDs only. It never writes evaluator fields to
the candidate manifest and refuses to sample if the downloaded dataset does
not exactly match the committed 50-ID pool fingerprint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path


def _fingerprint(ids: list[str]) -> str:
    return hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()


def _pool(path: Path) -> list[str]:
    ids = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(ids) != len(set(ids)):
        raise ValueError("pool file contains duplicate instance IDs")
    return ids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="MariusHobbhahn/swe-bench-verified-mini")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--split", default="test")
    parser.add_argument("--pool-file", type=Path, default=Path("tasks/verified_mini_pool.txt"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--output", type=Path, default=Path("tasks/evaluation.selection.json"))
    args = parser.parse_args()
    if args.count <= 0:
        raise SystemExit("--count must be positive")

    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise SystemExit("install requirements-evaluation.txt before selecting from the dataset") from exc

    committed_pool = _pool(args.pool_file)
    dataset = load_dataset(args.dataset, revision=args.revision, split=args.split)
    dataset_ids = [str(row["instance_id"]) for row in dataset]
    if sorted(dataset_ids) != sorted(committed_pool):
        raise SystemExit("downloaded dataset IDs do not match tasks/verified_mini_pool.txt")
    if args.count > len(committed_pool):
        raise SystemExit("--count exceeds the verified mini pool")

    ordered_pool = sorted(committed_pool)
    selected = random.Random(args.seed).sample(ordered_pool, args.count)
    payload = {
        "dataset_name": args.dataset,
        "dataset_revision": args.revision,
        "split": args.split,
        "pool_count": len(ordered_pool),
        "pool_ids_sha256": _fingerprint(ordered_pool),
        "seed": args.seed,
        "count": args.count,
        "algorithm": "sorted instance IDs; random.Random(seed).sample(pool, count)",
        "selected_ids_sha256": _fingerprint(selected),
        "selected_ids": selected,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
