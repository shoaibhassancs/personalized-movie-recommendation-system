"""Step 7 content-based model: TF-IDF item features and a rating-centred user profile.

Item features are four blocks: genres, normalised tags, title words and decade. Each
block is L2-normalised, multiplied by its weight (all 1.0, provisional) and stacked,
then the whole vector is L2-normalised so a dot product is a cosine similarity.

Tags come only from ``FitData.tags``, which the split already limited to tags earlier
than their author's own cutoff; the tag vocabulary and IDF are fitted on those tags
alone. Genres, titles and years are catalogue facts, not ratings or tags. The all-tags
version belongs to serving artifacts (Step 17), not here.

User profile: weight each history item by (its rating minus the user's own mean rating),
keep the items rated above that mean, and take the weighted average of their vectors. A
user whose ratings are all equal has no above-average items, so every history item is
used with weight equal to its rating. An empty history gives all-zero scores; the
cold-start ladder (Step 10) is what handles that case.
"""

import re
from collections.abc import Iterable
from typing import Self

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from pmrs.recommender.base import FitData, FloatArray, History, Scorer

DEFAULT_WEIGHTS = {"genres": 1.0, "tags": 1.0, "title": 1.0, "decade": 1.0}
_WORD = r"(?u)\b[a-z][a-z]+\b"
_SPACES = re.compile(r"\s+")


def normalise_tag(tag: str) -> str:
    """Lower-case, trim and collapse spaces; an empty result means "no tag"."""
    return _SPACES.sub(" ", tag.strip().lower())


def genre_names(value: str | Iterable[str]) -> list[str]:
    """Lower-case genre names from the loader's tuple form, or from an "A|B" string.

    "(no genres listed)" and empty values give no genres.
    """
    raw = value.split("|") if isinstance(value, str) else list(value)
    names = [str(g).strip().lower() for g in raw]
    return [n for n in names if n and not n.startswith("(no genres")]


def _genre_docs(movies: pd.DataFrame) -> list[str]:
    return [" ".join(genre_names(genres)) for genres in movies["genres"]]


def _decade_docs(movies: pd.DataFrame) -> list[str]:
    years = pd.to_numeric(movies["year"], errors="coerce")
    return [f"d{int(y) // 10 * 10}" if pd.notna(y) else "" for y in years]


def _tag_docs(data: FitData) -> list[str]:
    tags = data.tags
    docs = [""] * len(data.item_map)
    if tags.empty:
        return docs
    clean = tags["tag"].astype(str).map(normalise_tag)
    positions = data.item_map.to_index(tags["movie_id"])
    grouped: dict[int, list[str]] = {}
    for position, tag in zip(positions.tolist(), clean.tolist(), strict=True):
        if tag:
            grouped.setdefault(position, []).append(tag)
    for position, words in grouped.items():
        docs[position] = " ".join(words)
    return docs


def _block(
    docs: list[str], vectorizer: TfidfVectorizer, weight: float
) -> "sparse.csr_matrix":
    """TF-IDF block, L2-normalised rows times weight; no usable words: no columns."""
    empty = sparse.csr_matrix((len(docs), 0), dtype=np.float64)
    if not any(doc.strip() for doc in docs):
        return empty
    try:
        matrix = vectorizer.fit_transform(docs)
    except ValueError as error:
        # e.g. every title is a number or a stop word ("1984", "It"): nothing to learn
        if "empty vocabulary" not in str(error):
            raise
        return empty
    return sparse.csr_matrix(normalize(matrix) * weight)


class ContentScorer(Scorer):
    """Cosine similarity between a user's taste profile and every movie."""

    def __init__(
        self,
        use_tags: bool = True,
        weights: dict[str, float] | None = None,
    ) -> None:
        self.use_tags = use_tags
        self.weights = {**DEFAULT_WEIGHTS, **(weights or {})}
        self.name = "content" if use_tags else "content_no_tags"

    def fit(self, data: FitData) -> Self:
        self.item_map = data.item_map
        movies = data.movies
        w = self.weights
        blocks = [
            _block(
                _genre_docs(movies),
                TfidfVectorizer(analyzer=str.split, lowercase=False),
                w["genres"],
            ),
            _block(
                movies["title_clean"].fillna("").astype(str).tolist(),
                TfidfVectorizer(token_pattern=_WORD, stop_words="english"),
                w["title"],
            ),
            _block(
                _decade_docs(movies),
                TfidfVectorizer(analyzer=str.split, lowercase=False),
                w["decade"],
            ),
        ]
        if self.use_tags:
            blocks.append(
                _block(
                    _tag_docs(data),
                    TfidfVectorizer(token_pattern=_WORD),
                    w["tags"],
                )
            )
        stacked = sparse.hstack(blocks, format="csr", dtype=np.float64)
        if stacked.shape[1] == 0:  # no features at all: every score will be zero
            self.item_vectors: sparse.csr_matrix = sparse.csr_matrix(stacked)
        else:
            self.item_vectors = sparse.csr_matrix(normalize(stacked))
        return self

    def profile(self, history: History) -> FloatArray:
        """The user's taste vector (unit length), or zeros if nothing can be built."""
        width = self.item_vectors.shape[1]
        if len(history) == 0:
            return np.zeros(width)
        weights = history.ratings - history.ratings.mean()
        chosen = weights > 0
        if not chosen.any():
            weights, chosen = history.ratings, np.ones(len(history), dtype=bool)
        vectors = self.item_vectors[history.items[chosen]]
        mixed = np.asarray(vectors.T @ weights[chosen], dtype=np.float64).ravel()
        length = float(np.linalg.norm(mixed))
        return mixed / length if length > 0 else mixed

    def score(self, history: History) -> FloatArray:
        return np.asarray(
            self.item_vectors @ self.profile(history), dtype=np.float64
        ).ravel()
