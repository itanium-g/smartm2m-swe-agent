"""Offline result normalization and conservative paired reporting."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class TaskOutcome:
    instance_id: str
    generation_status: str
    evaluation_status: str
    resolved: bool
    reason: str = ""
    patch_sha256: str = ""
    cost_usd: float | None = None


def _bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "resolved", "pass", "passed"}:
            return True
        if normalized in {"0", "false", "no", "unresolved", "fail", "failed"}:
            return False
    return None


def _evaluation_value(record: dict[str, Any]) -> tuple[bool, str]:
    for key in ("resolved", "success", "passed", "is_resolved"):
        value = _bool(record.get(key))
        if value is not None:
            return value, "" if value else str(record.get("reason", record.get("error", "tests failed")))
    nested = record.get("tests_status")
    if isinstance(nested, dict):
        fail = nested.get("FAIL_TO_PASS", nested.get("fail_to_pass"))
        keep = nested.get("PASS_TO_PASS", nested.get("pass_to_pass"))
        if isinstance(fail, dict):
            fail = all(_bool(value) is True for value in fail.values())
        if isinstance(keep, dict):
            keep = all(_bool(value) is True for value in keep.values())
        if fail is not None and keep is not None:
            ok = bool(fail) and bool(keep)
            return ok, "" if ok else "FAIL_TO_PASS or PASS_TO_PASS failed"
    return False, str(record.get("reason", record.get("error", "unparseable evaluation record")))


def load_records(path: str | Path) -> dict[str, dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return {}
    if source.is_dir():
        files = sorted([
            *source.glob("*.json"),
            *source.glob("*.jsonl"),
            *source.rglob("*.json"),
            *source.rglob("*.jsonl"),
        ])
    else:
        files = [source]
    output: dict[str, dict[str, Any]] = {}
    for file in dict.fromkeys(files):
        try:
            if file.suffix == ".jsonl":
                values = [
                    json.loads(line)
                    for line in file.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            else:
                parsed = json.loads(file.read_text(encoding="utf-8"))
                if isinstance(parsed, list):
                    values = parsed
                elif isinstance(parsed, dict) and isinstance(parsed.get("results"), list):
                    values = parsed["results"]
                else:
                    values = [parsed]
        except (OSError, json.JSONDecodeError, AttributeError):
            continue
        for value in values:
            if isinstance(value, dict) and value.get("instance_id"):
                output[str(value["instance_id"])] = value
    return output


def outcomes_for_tasks(
    task_ids: Iterable[str],
    generation: dict[str, dict[str, Any]],
    evaluation: dict[str, dict[str, Any]],
) -> list[TaskOutcome]:
    outcomes: list[TaskOutcome] = []
    for instance_id in task_ids:
        generated = generation.get(instance_id, {})
        evaluated = evaluation.get(instance_id, {})
        resolved, reason = _evaluation_value(evaluated) if evaluated else (False, "not evaluated")
        cost = generated.get("estimated_cost_usd")
        outcomes.append(TaskOutcome(
            instance_id=instance_id,
            generation_status=str(generated.get("status", "missing")),
            evaluation_status="resolved" if resolved else str(evaluated.get("status", "not_evaluated")),
            resolved=resolved,
            reason=reason,
            patch_sha256=str(generated.get("patch_sha256", "")),
            cost_usd=float(cost) if cost is not None else None,
        ))
    return outcomes


def summary_for_pairs(
    task_ids: Iterable[str],
    baseline: list[TaskOutcome],
    custom: list[TaskOutcome],
    expected_count: int,
) -> dict[str, Any]:
    baseline_map = {row.instance_id: row for row in baseline}
    custom_map = {row.instance_id: row for row in custom}
    ids = list(task_ids)
    pairs = {
        "both_solved": 0,
        "custom_only": 0,
        "reference_only": 0,
        "neither_verified": 0,
    }
    for instance_id in ids:
        b = baseline_map.get(instance_id, TaskOutcome(instance_id, "missing", "not_evaluated", False))
        c = custom_map.get(instance_id, TaskOutcome(instance_id, "missing", "not_evaluated", False))
        if b.resolved and c.resolved:
            pairs["both_solved"] += 1
        elif c.resolved:
            pairs["custom_only"] += 1
        elif b.resolved:
            pairs["reference_only"] += 1
        else:
            pairs["neither_verified"] += 1
    b_count = sum(row.resolved for row in baseline)
    c_count = sum(row.resolved for row in custom)
    return {
        "expected_count": expected_count,
        "reference_resolved": b_count,
        "custom_resolved": c_count,
        "reference_percent_resolved": round(100 * b_count / expected_count, 4) if expected_count else 0.0,
        "custom_percent_resolved": round(100 * c_count / expected_count, 4) if expected_count else 0.0,
        "lift_percentage_points": round(100 * (c_count - b_count) / expected_count, 4) if expected_count else 0.0,
        "pairs": pairs,
        "baseline": [row.__dict__ for row in baseline],
        "custom": [row.__dict__ for row in custom],
    }


def write_summary(path: str | Path, summary: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    baseline = {row["instance_id"]: row for row in summary.get("baseline", [])}
    custom = {row["instance_id"]: row for row in summary.get("custom", [])}
    lines = [
        "# SMARTM2M Track 3 results",
        "",
        "This table is generated from recorded official evaluation records. "
        "Missing or unverified tasks count as unresolved.",
        "",
        f"- Reference: **{summary.get('reference_percent_resolved', 0)}%** "
        f"({summary.get('reference_resolved', 0)}/{summary.get('expected_count', 0)})",
        f"- Custom: **{summary.get('custom_percent_resolved', 0)}%** "
        f"({summary.get('custom_resolved', 0)}/{summary.get('expected_count', 0)})",
        f"- Lift: **{summary.get('lift_percentage_points', 0)} percentage points**",
        "",
        "| Instance | Reference | Custom | Reference generation | Custom generation | Reason |",
        "|---|---:|---:|---|---|---|",
    ]
    for instance_id in sorted(set(baseline) | set(custom)):
        b, c = baseline.get(instance_id, {}), custom.get(instance_id, {})
        reason = str(c.get("reason") or b.get("reason") or "").replace("|", "\\|")
        lines.append(
            f"| {instance_id} | {'yes' if b.get('resolved') else 'no'} | "
            f"{'yes' if c.get('resolved') else 'no'} | {b.get('generation_status', 'missing')} | "
            f"{c.get('generation_status', 'missing')} | {reason} |"
        )
    lines.extend([
        "",
        "## Paired outcomes",
        "",
        "| Both solved | Custom only | Reference only | Neither verified |",
        "|---:|---:|---:|---:|",
        f"| {summary.get('pairs', {}).get('both_solved', 0)} | "
        f"{summary.get('pairs', {}).get('custom_only', 0)} | "
        f"{summary.get('pairs', {}).get('reference_only', 0)} | "
        f"{summary.get('pairs', {}).get('neither_verified', 0)} |",
        "",
    ])
    target.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")


def hash_result_bundle(root: str | Path) -> str:
    base = Path(root)
    digest = hashlib.sha256()
    for path in sorted(base.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(base).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()
