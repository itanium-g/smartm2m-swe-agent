from smartm2m.reporting import outcomes_for_tasks, summary_for_pairs


def test_paired_summary_uses_fixed_denominator():
    ids = ["a", "b", "c", "d"]
    baseline = outcomes_for_tasks(
        ids,
        {
            "a": {"instance_id": "a", "status": "submitted"},
            "b": {"instance_id": "b", "status": "submitted"},
        },
        {
            "a": {"instance_id": "a", "resolved": True},
            "b": {"instance_id": "b", "resolved": False},
        },
    )
    custom = outcomes_for_tasks(
        ids,
        {
            "a": {"instance_id": "a", "status": "submitted"},
            "b": {"instance_id": "b", "status": "submitted"},
            "c": {"instance_id": "c", "status": "submitted"},
        },
        {
            "a": {"instance_id": "a", "resolved": True},
            "b": {"instance_id": "b", "resolved": True},
            "c": {"instance_id": "c", "resolved": True},
        },
    )
    summary = summary_for_pairs(ids, baseline, custom, 4)
    assert summary["reference_resolved"] == 1
    assert summary["custom_resolved"] == 3
    assert summary["reference_percent_resolved"] == 25.0
    assert summary["custom_percent_resolved"] == 75.0
    assert summary["lift_percentage_points"] == 50.0
    assert summary["pairs"] == {
        "both_solved": 1,
        "custom_only": 2,
        "reference_only": 0,
        "neither_verified": 1,
    }
