"""ID maps and the sparse user-item interaction matrix."""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd
from scipy import sparse


@dataclass(frozen=True)
class IdMap:
    """Maps raw MovieLens IDs to dense row/column positions 0..n-1.

    Positions follow ascending ID order, so the mapping is deterministic.
    """

    ids: npt.NDArray[np.int64]

    @classmethod
    def from_ids(cls, values: "pd.Series[int] | npt.NDArray[np.int64]") -> "IdMap":
        unique = np.unique(np.asarray(values, dtype=np.int64))
        return cls(ids=unique)

    def __len__(self) -> int:
        return int(self.ids.size)

    def __contains__(self, raw_id: int) -> bool:
        position = int(np.searchsorted(self.ids, raw_id))
        return position < self.ids.size and int(self.ids[position]) == raw_id

    def to_index(
        self, values: "pd.Series[int] | npt.NDArray[np.int64]"
    ) -> npt.NDArray[np.intp]:
        """Positions for raw IDs; raises KeyError if any ID is not in the map."""
        raw = np.asarray(values, dtype=np.int64)
        positions = np.searchsorted(self.ids, raw)
        clipped = np.minimum(positions, max(self.ids.size - 1, 0))
        if raw.size and (
            self.ids.size == 0 or not np.array_equal(self.ids[clipped], raw)
        ):
            missing = np.setdiff1d(raw, self.ids)
            raise KeyError(f"IDs not in the map: {missing[:5].tolist()}")
        return positions.astype(np.intp)


def build_interaction_matrix(
    ratings: pd.DataFrame, user_map: IdMap, item_map: IdMap
) -> "sparse.csr_matrix":
    """Users x items matrix holding the rating value (0.5 to 5), CSR format.

    Users or items with no rows stay as empty rows/columns, so the shape is always
    ``(len(user_map), len(item_map))``. A repeated (user, movie) pair is an error.
    """
    if ratings.duplicated(["user_id", "movie_id"]).any():
        raise ValueError("duplicate (user_id, movie_id) pairs in ratings")
    rows = user_map.to_index(ratings["user_id"])
    cols = item_map.to_index(ratings["movie_id"])
    values = ratings["rating"].to_numpy(dtype=np.float64)
    matrix = sparse.coo_matrix(
        (values, (rows, cols)), shape=(len(user_map), len(item_map))
    )
    return matrix.tocsr()
