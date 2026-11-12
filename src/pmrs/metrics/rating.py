"""Step 13 rating-error metrics: RMSE and MAE.

These compare predicted ratings with the ratings users actually gave. They answer a
different question from the ranking metrics (how close is the number, not whether the
right movies are at the top), and a method can be good at one and poor at the other.
Empty input gives NaN rather than a misleading 0.
"""

import math

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]


def _errors(predicted: FloatArray, actual: FloatArray) -> FloatArray:
    if predicted.shape != actual.shape:
        raise ValueError("predicted and actual must have the same shape")
    return np.asarray(predicted - actual, dtype=np.float64)


def rmse(predicted: FloatArray, actual: FloatArray) -> float:
    """Root mean squared error; large misses count extra."""
    errors = _errors(predicted, actual)
    return float(np.sqrt(np.mean(errors**2))) if errors.size else math.nan


def mae(predicted: FloatArray, actual: FloatArray) -> float:
    """Mean absolute error; every miss counts in proportion to its size."""
    errors = _errors(predicted, actual)
    return float(np.mean(np.abs(errors))) if errors.size else math.nan
