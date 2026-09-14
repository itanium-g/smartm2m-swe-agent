import json
from pathlib import Path

from smartm2m.reporting import load_records


def test_load_records_normalizes_swebench_instance_map(tmp_path: Path):
    (tmp_path / "report.json").write_text(
        json.dumps({"django__django-1": {"resolved": True, "tests_status": {}}}),
        encoding="utf-8",
    )

    records = load_records(tmp_path)

    assert records["django__django-1"]["resolved"] is True
    assert records["django__django-1"]["instance_id"] == "django__django-1"


def test_load_records_normalizes_swebench_run_summary(tmp_path: Path):
    (tmp_path / "results.json").write_text(
        json.dumps({
            "resolved_ids": ["a"],
            "unresolved_ids": ["b"],
            "error_ids": ["c"],
        }),
        encoding="utf-8",
    )

    records = load_records(tmp_path)

    assert records["a"]["resolved"] is True
    assert records["b"]["resolved"] is False
    assert records["c"]["status"] == "not_resolved"
