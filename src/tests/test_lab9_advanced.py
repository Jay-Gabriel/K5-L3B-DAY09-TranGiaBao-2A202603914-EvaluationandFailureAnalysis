"""M5-M7 self-check (Advanced/Expert). Run: python -m pytest -q -m student -o addopts= -k advanced
Public vectors only; the instructor grades with hidden ones."""
import copy
import math
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.student


@pytest.fixture(scope="module")
def stats():
    from lab9 import stats

    return stats


@pytest.mark.parametrize("n,c,k,want", [(5, 5, 5, 1.0), (5, 0, 1, 0.0), (5, 2, 1, 0.4), (10, 3, 3, 1 - 35 / 120)])
def test_pass_at_k(stats, n, c, k, want):
    assert math.isclose(stats.pass_at_k(n, c, k), want, abs_tol=1e-9)


@pytest.mark.parametrize("n,c,k,want", [(5, 5, 5, 1.0), (5, 4, 5, 0.0), (5, 4, 3, 0.4), (10, 8, 2, 28 / 45)])
def test_pass_hat_k(stats, n, c, k, want):
    assert math.isclose(stats.pass_hat_k(n, c, k), want, abs_tol=1e-9)


def test_pass_k_rejects_bad_args(stats):
    for args in [(5, 6, 1), (5, 2, 0), (3, 1, 4)]:
        with pytest.raises(ValueError):
            stats.pass_at_k(*args)


@pytest.mark.parametrize("function_name", ["pass_at_k", "pass_hat_k"])
@pytest.mark.parametrize("args", [
    (0, 0, 1), (-1, 0, 1), (5, -1, 1), (5, 6, 1), (5, 2, 0), (5, 2, 6), (5.5, 2, 1),
])
def test_pass_estimators_reject_invalid_domains(stats, function_name, args):
    with pytest.raises(ValueError):
        getattr(stats, function_name)(*args)


def _report(rows, metrics, items=4, seeds=(1, 2)):
    return {"manifest": {"eval_set_sha": "x", "items": items, "seeds": list(seeds)},
            "rows": rows, "metrics": metrics, "evaluator_failures": []}


ROWS = [{"item_id": f"E-{i:03d}", "seed": s, "pass_rate": True, "slices": ["denial"] if i < 2 else []}
        for i in range(4) for s in (1, 2)]
SPEC = {"eval_set_version": "v2", "metrics": [{"id": "pass_rate", "kind": "capability", "blocking": True,
                                               "threshold": {"min": 0.8}}]}


def test_integrity_flags_nan_and_dropped_rows():
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0})
    assert gate.integrity_check(base, base, SPEC) == []
    nan = _report(copy.deepcopy(ROWS), {"pass_rate": float("nan")})
    assert gate.integrity_check(nan, base, SPEC)
    dropped = _report(copy.deepcopy(ROWS[:-1]), {"pass_rate": 1.0})
    assert gate.integrity_check(dropped, base, SPEC)


@pytest.mark.parametrize("value", [math.inf, -math.inf])
def test_integrity_flags_infinite_metrics(value):
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0})
    pr = _report(copy.deepcopy(ROWS), {"pass_rate": value})
    assert gate.integrity_check(pr, base, SPEC)


def test_integrity_flags_evaluator_failures_and_missing_row_metric():
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0})
    failed = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0})
    failed["evaluator_failures"] = ["E-001@1:pass_rate:grader crashed"]
    assert gate.integrity_check(failed, base, SPEC)

    missing = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0})
    del missing["rows"][0]["pass_rate"]
    assert gate.integrity_check(missing, base, SPEC)


def test_integrity_flags_duplicate_keys_and_relabelled_slices():
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0})
    duplicate = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0})
    duplicate["rows"][-1] = copy.deepcopy(duplicate["rows"][-2])
    assert gate.integrity_check(duplicate, base, SPEC)

    relabelled = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0})
    relabelled["rows"][0]["slices"] = []
    assert gate.integrity_check(relabelled, base, SPEC)


def test_integrity_flags_loosened_spec():
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0})
    loose = copy.deepcopy(SPEC)
    loose["metrics"][0]["threshold"]["min"] = 0.5
    assert gate.integrity_check(base, base, loose, SPEC)
    assert gate.integrity_check(base, base, SPEC, SPEC) == []


def test_integrity_flags_removed_metric_and_blocking_floor():
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0})
    removed = copy.deepcopy(SPEC)
    removed["metrics"] = []
    assert gate.integrity_check(base, base, removed, SPEC)

    nonblocking = copy.deepcopy(SPEC)
    nonblocking["metrics"][0]["blocking"] = False
    assert gate.integrity_check(base, base, nonblocking, SPEC)


def test_integrity_flags_removed_significance_rule_and_slice():
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0})
    strict = copy.deepcopy(SPEC)
    strict["metrics"][0]["threshold"]["no_significant_drop"] = True
    no_ci = copy.deepcopy(strict)
    del no_ci["metrics"][0]["threshold"]["no_significant_drop"]
    assert gate.integrity_check(base, base, no_ci, strict)

    with_slice = copy.deepcopy(SPEC)
    with_slice["slices"] = [{"name": "denial", "metric": "pass_rate", "min": 0.9, "blocking": True}]
    no_slice = copy.deepcopy(with_slice)
    no_slice["slices"] = []
    assert gate.integrity_check(base, base, no_slice, with_slice)


@pytest.mark.parametrize("new_threshold", [{"max_increase": 0.2}, {}])
def test_integrity_rejects_relaxed_max_increase(new_threshold):
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0, "cost_per_success": 10.0})
    old = copy.deepcopy(SPEC)
    old["metrics"].append({"id": "cost_per_success", "threshold": {"max_increase": 0.1}})
    new = copy.deepcopy(old)
    new["metrics"][-1]["threshold"] = new_threshold
    assert gate.integrity_check(base, base, new, old)


def test_slice_check_blocks_a_slice_below_floor():
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0})
    rows = copy.deepcopy(ROWS)
    for r in rows:
        if "denial" in r["slices"] and r["seed"] == 1:
            r["pass_rate"] = False
    spec = dict(SPEC, slices=[{"name": "denial", "metric": "pass_rate", "min": 0.9, "blocking": True}])
    blocked, _ = gate.slice_check(_report(rows, {"pass_rate": 0.75}), base, spec)
    assert blocked == ["slice:denial/pass_rate"]


def test_slice_check_blocks_significant_paired_drop_above_floor():
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0})
    rows = copy.deepcopy(ROWS)
    for row in rows:
        if "denial" in row["slices"] and row["seed"] == 1:
            row["pass_rate"] = False
    spec = copy.deepcopy(SPEC)
    spec["slices"] = [{"name": "denial", "metric": "pass_rate", "min": 0.4,
                       "no_significant_drop": True, "blocking": True}]
    blocked, _ = gate.slice_check(_report(rows, {"pass_rate": 0.75}), base, spec)
    assert blocked == ["slice:denial/pass_rate"]


def test_slice_check_blocks_slice_with_no_pr_rows():
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0})
    pr = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0})
    for row in pr["rows"]:
        row["slices"] = []
    spec = copy.deepcopy(SPEC)
    spec["slices"] = [{"name": "adversarial", "metric": "pass_rate", "min": 0.9, "blocking": True}]
    blocked, _ = gate.slice_check(pr, base, spec)
    assert blocked == ["slice:adversarial/pass_rate"]


def test_v2_spec_has_blocking_fm08_pass_hat_and_required_slices():
    spec_path = Path(__file__).resolve().parents[1] / "config/metric_spec_v2.yaml"
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    metrics = {metric["id"]: metric for metric in spec["metrics"]}
    assert metrics["reply_matches_ledger"]["blocking"] is True
    assert metrics["pass_hat_5"]["blocking"] is True
    assert metrics["pass_hat_5"]["threshold"]["min"] >= 0.8
    slices = {slice_spec["name"] for slice_spec in spec["slices"]}
    assert {"money_movement", "adversarial"} <= slices
