import json
from pathlib import Path

from smartm2m.smoke import run_smoke


def test_offline_smoke_produces_paired_result(tmp_path: Path):
    output = run_smoke(tmp_path / "smoke")
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["kind"] == "synthetic_smoke"
    assert summary["custom_percent_resolved"] == 100.0
    assert summary["reference_percent_resolved"] == 0.0
    assert (output / "checksums.sha256").is_file()
