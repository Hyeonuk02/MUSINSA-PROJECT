"""fault_check --impact: 재생하지 않은 target을 분리한다."""
import fault_check


def test_split_replayed_separates_not_replayed():
    targets = {"R1/0": "CV", "R2/0": "CV"}
    base = {"R1/0": {}, "R3/0": {}}
    inside, b, missed = fault_check.split_replayed(targets, base, {"R1"})
    assert inside == {"R1/0": "CV"} and set(b) == {"R1/0"} and missed == ["R2/0"]


def test_split_replayed_without_impact_keeps_all():
    targets = {"R1/0": "CV"}
    assert fault_check.split_replayed(targets, {}, None) == (targets, {}, [])
