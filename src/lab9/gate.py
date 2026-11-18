"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []

    def inspect_report(name: str, report: dict) -> tuple[set[tuple[str, int]], dict[tuple[str, int], set[str]]]:
        manifest = report.get("manifest") or {}
        rows = report.get("rows")
        metrics = report.get("metrics")
        if not isinstance(rows, list):
            problems.append(f"{name}.rows is missing or is not a list")
            rows = []
        if not isinstance(metrics, dict):
            problems.append(f"{name}.metrics is missing or is not an object")
            metrics = {}

        item_count = manifest.get("items")
        seeds = manifest.get("seeds")
        if not isinstance(item_count, int) or isinstance(item_count, bool) or item_count < 0:
            problems.append(f"{name}.manifest.items is invalid")
            item_count = -1
        if not isinstance(seeds, list) or any(not isinstance(s, int) or isinstance(s, bool) for s in seeds):
            problems.append(f"{name}.manifest.seeds is invalid")
            seeds = []
        if len(set(seeds)) != len(seeds):
            problems.append(f"{name}.manifest.seeds contains duplicates")

        keys: list[tuple[str, int]] = []
        slice_tags: dict[tuple[str, int], set[str]] = {}
        item_ids: set[str] = set()
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                problems.append(f"{name}.rows[{index}] is not an object")
                continue
            item_id, seed = row.get("item_id"), row.get("seed")
            if not isinstance(item_id, str) or not item_id or not isinstance(seed, int) or isinstance(seed, bool):
                problems.append(f"{name}.rows[{index}] has an invalid item_id/seed")
                continue
            key = (item_id, seed)
            keys.append(key)
            item_ids.add(item_id)
            tags = row.get("slices") or []
            if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
                problems.append(f"{name}.rows[{index}].slices is invalid")
                tags = []
            if len(set(tags)) != len(tags):
                problems.append(f"{name}.rows[{index}].slices contains duplicates")
            slice_tags[key] = set(tags)

        key_set = set(keys)
        if len(key_set) != len(keys):
            problems.append(f"{name}.rows contains duplicate (item_id, seed) keys")
        if item_count >= 0 and len(rows) != item_count * len(seeds):
            problems.append(f"{name}.rows count {len(rows)} != manifest items × seeds ({item_count * len(seeds)})")
        if item_count >= 0 and len(item_ids) != item_count:
            problems.append(f"{name}.rows has {len(item_ids)} distinct items, manifest says {item_count}")
        if seeds and item_ids:
            expected = {(item, seed) for item in item_ids for seed in seeds}
            if key_set != expected:
                problems.append(f"{name}.rows does not contain every item × manifest seed pair")

        for metric in spec.get("metrics", []):
            metric_id = metric.get("id")
            if not metric_id:
                continue
            value = metrics.get(metric_id)
            if metric_id not in metrics:
                problems.append(f"{name}.metrics is missing {metric_id}")
            elif not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
                problems.append(f"{name}.metrics.{metric_id} is not a finite number")

            # These values are derived across rows rather than emitted for each row.
            row_derived = metric_id == "pass_5" or metric_id == "cost_per_success" or \
                metric_id.startswith("pass_at_") or metric_id.startswith("pass_hat_")
            if not row_derived:
                for index, row in enumerate(rows):
                    if not isinstance(row, dict):
                        continue
                    if metric_id not in row:
                        problems.append(f"{name}.rows[{index}] is missing {metric_id}")
                        break
                    row_value = row[metric_id]
                    if row_value is None:
                        problems.append(f"{name}.rows[{index}].{metric_id} is missing (grader failure)")
                        break
                    if isinstance(row_value, (int, float)) and not isinstance(row_value, bool) \
                            and not math.isfinite(float(row_value)):
                        problems.append(f"{name}.rows[{index}].{metric_id} is not finite")
                        break

        failures = report.get("evaluator_failures")
        if not isinstance(failures, list) or failures:
            problems.append(f"{name}.evaluator_failures is missing or non-empty")
        return key_set, slice_tags

    pr_keys, pr_slices = inspect_report("pr", pr)
    base_keys, base_slices = inspect_report("baseline", base)
    if pr_keys != base_keys:
        problems.append("PR (item_id, seed) set differs from baseline")
    for key in sorted(pr_keys & base_keys):
        if pr_slices.get(key, set()) != base_slices.get(key, set()):
            problems.append(f"slice tags changed for {key[0]}@{key[1]}")

    if base_spec and base_spec.get("eval_set_version") == spec.get("eval_set_version"):
        current_metrics = {m.get("id"): m for m in spec.get("metrics", []) if m.get("id")}
        for old in base_spec.get("metrics", []):
            metric_id = old.get("id")
            if not metric_id:
                continue
            new = current_metrics.get(metric_id)
            if new is None:
                problems.append(f"ratchet removed metric {metric_id}")
                continue
            if old.get("blocking") and not new.get("blocking"):
                problems.append(f"ratchet made {metric_id} non-blocking")
            old_threshold = old.get("threshold") or {}
            new_threshold = new.get("threshold") or {}
            if "min" in old_threshold and ("min" not in new_threshold or new_threshold["min"] < old_threshold["min"]):
                problems.append(f"ratchet lowered minimum for {metric_id}")
            if "max" in old_threshold and ("max" not in new_threshold or new_threshold["max"] > old_threshold["max"]):
                problems.append(f"ratchet raised maximum for {metric_id}")
            if "max_increase" in old_threshold and ("max_increase" not in new_threshold or new_threshold["max_increase"] > old_threshold["max_increase"]):
                problems.append(f"ratchet raised max_increase for {metric_id}")
            if old_threshold.get("no_significant_drop") and not new_threshold.get("no_significant_drop"):
                problems.append(f"ratchet removed no_significant_drop for {metric_id}")

        current_slices = {(s.get("name"), s.get("metric")): s for s in spec.get("slices", [])}
        for old in base_spec.get("slices", []):
            key = (old.get("name"), old.get("metric"))
            new = current_slices.get(key)
            label = f"{key[0]}/{key[1]}"
            if new is None:
                problems.append(f"ratchet removed slice {label}")
                continue
            if old.get("blocking") and not new.get("blocking"):
                problems.append(f"ratchet made slice {label} non-blocking")
            if "min" in old and ("min" not in new or new["min"] < old["min"]):
                problems.append(f"ratchet lowered minimum for slice {label}")
            if "max" in old and ("max" not in new or new["max"] > old["max"]):
                problems.append(f"ratchet raised maximum for slice {label}")
            if old.get("no_significant_drop") and not new.get("no_significant_drop"):
                problems.append(f"ratchet removed no_significant_drop for slice {label}")
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bootstrap = spec.get("bootstrap", {})
    for slice_spec in spec.get("slices", []):
        name, metric = slice_spec["name"], slice_spec["metric"]
        identifier = f"slice:{name}/{metric}"
        values = per_item(pr, metric, slice_name=name)
        baseline_values = per_item(base, metric, slice_name=name)
        if not values:
            verdict = "missing slice data"
            value = None
            note = ""
            failed = True
        else:
            value = sum(values.values()) / len(values)
            failed = False
            notes = []
            threshold = slice_spec
            if "min" in threshold and value < threshold["min"]:
                failed = True
                notes.append(f"below min {threshold['min']}")
            if "max" in threshold and value > threshold["max"]:
                failed = True
                notes.append(f"above max {threshold['max']}")
            if threshold.get("no_significant_drop"):
                common = sorted(set(values) & set(baseline_values))
                if not common:
                    failed = True
                    notes.append("no paired baseline slice items")
                else:
                    delta, low, high = stats.paired_bootstrap(
                        [values[key] for key in common],
                        [baseline_values[key] for key in common],
                        n_resamples=bootstrap.get("n_resamples", 1000),
                        rng=bootstrap.get("rng", 2027),
                        confidence=bootstrap.get("confidence", 0.95),
                    )
                    notes.append(f"Δ {delta:+.3f} CI [{low:+.3f}, {high:+.3f}]")
                    if high < 0:
                        failed = True
            verdict = "; ".join(notes) if notes else "ok"
        if failed and slice_spec.get("blocking"):
            blocked.append(identifier)
            label = "BLOCK"
        else:
            label = "warn" if failed else "ok"
        lines.append(f"  {identifier:<36} {value!s:<8} {verdict:<40} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
