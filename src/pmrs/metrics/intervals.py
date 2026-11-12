"""Step 13 uncertainty: bootstrap confidence intervals over users.

The users we evaluated are a sample, so a mean metric would move if we had evaluated
different users. The bootstrap re-draws users with replacement many times, recomputes
the mean each time, and reports the middle 95% of those means. It describes **sampling
noise between users only**. It does not measure the split's leakage, the choice of
metric, or whether an offline gain would show up for real viewers.

``paired_bootstrap_difference`` compares two methods on the *same* users, which is much
tighter than comparing two separate intervals: a difference whose interval excludes 0 is
a difference that held across resamples of users (still only under this protocol).
"""

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]
DEFAULT_BOOTSTRAPS = 2000
DEFAULT_SEED = 42


def _check(values: FloatArray) -> FloatArray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1 or array.size == 0:
        raise ValueError("need a non-empty 1-D array of per-user values")
    if not np.isfinite(array).all():
        raise ValueError("per-user values must all be finite (no NaN or inf)")
    return array


def _draws(n: int, n_boot: int, seed: int) -> npt.NDArray[np.intp]:
    if n_boot < 1:
        raise ValueError("n_boot must be at least 1")
    return np.random.default_rng(seed).integers(0, n, size=(n_boot, n))


def _interval(means: FloatArray, level: float) -> tuple[float, float]:
    if not 0 < level < 1:
        raise ValueError("level must be between 0 and 1")
    tail = (1 - level) / 2 * 100
    low, high = np.percentile(means, [tail, 100 - tail])
    return float(low), float(high)


def bootstrap_ci(
    values: FloatArray,
    *,
    n_boot: int = DEFAULT_BOOTSTRAPS,
    level: float = 0.95,
    seed: int = DEFAULT_SEED,
) -> tuple[float, float, float]:
    """(mean, low, high) of ``values`` with a percentile bootstrap over users."""
    array = _check(values)
    means = array[_draws(array.size, n_boot, seed)].mean(axis=1)
    low, high = _interval(means, level)
    return float(array.mean()), low, high


def paired_bootstrap_difference(
    a: FloatArray,
    b: FloatArray,
    *,
    n_boot: int = DEFAULT_BOOTSTRAPS,
    level: float = 0.95,
    seed: int = DEFAULT_SEED,
) -> tuple[float, float, float]:
    """(mean of a - b, low, high) for two methods scored on the same users, in order."""
    left, right = _check(a), _check(b)
    if left.shape != right.shape:
        raise ValueError("paired values must cover the same users in the same order")
    return bootstrap_ci(left - right, n_boot=n_boot, level=level, seed=seed)


def bootstrap_ratio_ci(
    numerator: FloatArray,
    denominator: FloatArray,
    *,
    n_boot: int = DEFAULT_BOOTSTRAPS,
    level: float = 0.95,
    seed: int = DEFAULT_SEED,
) -> tuple[float, float, float]:
    """(sum num / sum den, low, high), re-drawing users. For pooled error rates.

    Each user contributes a numerator (e.g. their summed squared error) and a
    denominator (their number of held-out ratings), so users with more ratings weigh
    more, as in a pooled RMSE or MAE.
    """
    top, bottom = _check(numerator), _check(denominator)
    if top.shape != bottom.shape:
        raise ValueError("numerator and denominator must cover the same users")
    if bottom.sum() <= 0:
        raise ValueError("denominator must have a positive total")
    draws = _draws(top.size, n_boot, seed)
    ratios = top[draws].sum(axis=1) / bottom[draws].sum(axis=1)
    low, high = _interval(ratios, level)
    return float(top.sum() / bottom.sum()), low, high
