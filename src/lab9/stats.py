"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from numbers import Integral

import numpy as np
from scipy import stats as sp_stats

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    tp = sum(1 for h, j in zip(human, judge) if h == POS and j == POS)
    fp = sum(1 for h, j in zip(human, judge) if h != POS and j == POS)
    fn = sum(1 for h, j in zip(human, judge) if h == POS and j != POS)
    tn = sum(1 for h, j in zip(human, judge) if h != POS and j != POS)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    """precision = tp/(tp+fp), recall = tp/(tp+fn); return 0.0 when the denominator is 0."""
    cm = confusion(human, judge)
    tp, fp, fn = cm["tp"], cm["fp"], cm["fn"]
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    return float(prec), float(rec)


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    if len(human) != len(judge) or len(human) == 0:
        raise ValueError("Inputs must be non-empty and of equal length")
    n = len(human)
    po = sum(1 for h, j in zip(human, judge) if h == j) / n
    categories = sorted(set(human) | set(judge))
    pe = sum((human.count(c) / n) * (judge.count(c) / n) for c in categories)
    if math.isclose(pe, 1.0, rel_tol=1e-9, abs_tol=1e-9):
        raise ValueError("kappa undefined: constant judge (p_e == 1)")
    return (po - pe) / (1.0 - pe)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1]."""
    denom = sensitivity + specificity - 1.0
    if math.isclose(denom, 0.0, rel_tol=1e-9, abs_tol=1e-9):
        return max(0.0, min(1.0, observed_rate))
    corrected = (observed_rate + specificity - 1.0) / denom
    return float(max(0.0, min(1.0, corrected)))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    arr_a = np.asarray(a, dtype=float)
    arr_b = np.asarray(b, dtype=float)
    if np.array_equal(arr_a, arr_b):
        return (0.0, 0.0, 0.0)
    diff_mean = float(np.mean(arr_a) - np.mean(arr_b))
    res = sp_stats.bootstrap(
        (arr_a, arr_b),
        statistic=lambda x, y, axis: np.mean(x, axis=axis) - np.mean(y, axis=axis),
        paired=True,
        confidence_level=confidence,
        n_resamples=n_resamples,
        method="percentile",
        random_state=np.random.default_rng(rng),
    )
    return (diff_mean, float(res.confidence_interval.low), float(res.confidence_interval.high))


def _validate_pass_counts(n: int, c: int, k: int) -> tuple[int, int, int]:
    """Validate binomial-estimator counts and normalize integer-like values."""
    values = (n, c, k)
    if any(isinstance(value, bool) or not isinstance(value, Integral) for value in values):
        raise ValueError("n, c, and k must be integers")
    n, c, k = (int(value) for value in values)
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0 <= c <= n:
        raise ValueError("c must be between 0 and n")
    if not 1 <= k <= n:
        raise ValueError("k must be between 1 and n")
    return n, c, k


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k).
    Raise ValueError unless n > 0, 0 <= c <= n, and 1 <= k <= n."""
    n, c, k = _validate_pass_counts(n, c, k)
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError unless
    n > 0, 0 <= c <= n, and 1 <= k <= n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    n, c, k = _validate_pass_counts(n, c, k)
    if c < k:
        return 0.0
    return math.comb(c, k) / math.comb(n, k)
