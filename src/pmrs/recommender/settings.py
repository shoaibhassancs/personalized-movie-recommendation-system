"""Step 15: the model settings that tuning varies, in one frozen object.

``ModelSettings`` holds the single-model settings; the hybrid blend lives in
``HybridConfig``. The defaults are the provisional Phase 2 values, so
``ModelSettings()`` reproduces the untuned system exactly.
"""

from dataclasses import asdict, dataclass, field
from typing import Any

from pmrs.recommender.content import DEFAULT_WEIGHTS
from pmrs.recommender.knn import (
    DEFAULT_MIN_SUPPORT,
    DEFAULT_NEIGHBOURS,
    DEFAULT_SHRINKAGE,
)
from pmrs.recommender.svd import DEFAULT_FACTORS


@dataclass(frozen=True)
class ModelSettings:
    neighbours: int = DEFAULT_NEIGHBOURS
    shrinkage: float = DEFAULT_SHRINKAGE
    min_support: int = DEFAULT_MIN_SUPPORT
    factors: int = DEFAULT_FACTORS
    content_weights: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_WEIGHTS)
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ModelSettings":
        return cls(**raw)
