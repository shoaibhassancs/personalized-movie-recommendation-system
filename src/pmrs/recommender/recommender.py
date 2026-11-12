"""Step 12 single recommender interface.

One ``Recommender`` object holds every fitted model and is used the same way by
notebooks, the command line and (later) the API::

    rec = Recommender.fit(fit_data(split, movies, "validation"), target="validation")
    result = rec.recommend(UserProfile({318: 5.0, 296: 4.5}), strategy="hybrid", k=10)

The user is described by ``UserProfile``: the ratings they have (raw MovieLens movie id
to rating) and, optionally, favourite genre names (plain names such as ``"Sci-Fi"``).
Favourite genres are used only on the no-ratings rung of the ladder.

Candidate handling: a returned list never contains a movie in the profile. That is the
D-023 candidate rule: a warm user's known pre-cutoff movies, or a cold-start simulation
user's *revealed* movies only (nothing for zero revealed), with held-out movies still
eligible.

Leakage note (unchanged from Step 5): the models are fitted once, so they still see
other users' ratings and tags dated after a scored user's own cutoff. Anything measured
later supports only "methods compared under the same per-user holdout protocol".

Everything is provisional and untuned. Sample lists are a human spot check, not evidence
that any method recommends well.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

import numpy as np
import pandas as pd
import scipy
import sklearn

from pmrs.recommender.base import (
    MAX_RATING,
    MIN_RATING,
    FitData,
    History,
    IntArray,
    Scorer,
    rank_unseen,
)
from pmrs.recommender.baselines import (
    BayesianAverageScorer,
    PopularityScorer,
    RandomScorer,
)
from pmrs.recommender.content import ContentScorer
from pmrs.recommender.explain import Catalog, Evidence, render
from pmrs.recommender.hybrid import (
    COMPONENTS,
    Branch,
    HybridConfig,
    blend,
    genre_match,
    min_max_scale,
)
from pmrs.recommender.knn import ItemKNNScorer
from pmrs.recommender.settings import ModelSettings
from pmrs.recommender.svd import SVDScorer
from pmrs.split import IdMap

SCHEMA_VERSION = 1
STRATEGIES = (
    "hybrid",
    "popularity",
    "bayesian_average",
    "random",
    "content",
    "item_knn",
    "svd",
)
TRUSTED_ARTIFACT_WARNING = (
    "A .joblib file is a Python pickle: loading it can run any code stored in it. "
    "Only load artifacts this project built and kept in a place only you can write to. "
    "Never load one from a download, an email or an upload. The SHA-256 check only "
    "detects accidental damage and mix-ups; it cannot make an untrusted file safe."
)

ScoreKind = Literal[
    "hybrid blend (0 to 1)",
    "genre and popularity blend (0 to 1)",
    "rating count",
    "adjusted average rating",
    "random draw",
    "content similarity",
    "neighbour-weighted rating deviation",
    "latent-factor rating deviation",
]


@dataclass(frozen=True)
class UserProfile:
    """What the recommender is told about one user."""

    ratings: Mapping[int, float] = field(default_factory=dict)
    genres: tuple[str, ...] = ()  # favourite genres, plain names; used with no ratings


@dataclass(frozen=True)
class Recommendation:
    movie_id: int
    title: str
    genres: tuple[str, ...]
    score: float | None  # None: the method has no evidence for this movie
    explanation: str
    evidence: Evidence
    source: str  # the method whose evidence the explanation uses


@dataclass(frozen=True)
class RecommendationList:
    strategy: str
    branch: Branch | None  # the ladder rung (hybrid only)
    score_kind: ScoreKind
    items: tuple[Recommendation, ...]
    notes: tuple[str, ...] = ()

    @property
    def movie_ids(self) -> list[int]:
        return [item.movie_id for item in self.items]


@dataclass(frozen=True)
class ArtifactMetadata:
    """Version information saved beside the model file (data hash, date, seed)."""

    schema_version: int
    created_utc: str
    target: str
    seed: int
    data_hash: str
    n_items: int
    n_fit_users: int
    n_fit_ratings: int
    n_fit_tags: int
    libraries: dict[str, str]
    config: dict[str, Any]
    model_params: dict[str, dict[str, float | int | bool]]
    warning: str = TRUSTED_ARTIFACT_WARNING


def library_versions() -> dict[str, str]:
    return {
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scipy": scipy.__version__,
        "scikit-learn": sklearn.__version__,
    }


def display_genres(value: Any) -> tuple[str, ...]:
    """Genre display names from the loader's tuple form or an ``A|B`` string."""
    raw = value.split("|") if isinstance(value, str) else list(value)
    names = [str(g).strip() for g in raw]
    return tuple(n for n in names if n and not n.lower().startswith("(no genres"))


def _catalog(data: FitData) -> Catalog:
    movies = data.movies
    return Catalog(
        ids=data.item_map.ids.copy(),
        titles=[str(t) for t in movies["title"]],
        genres=[display_genres(g) for g in movies["genres"]],
    )


class Recommender:
    """All fitted models behind one ``recommend`` call. Build it with ``fit``."""

    def __init__(
        self,
        catalog: Catalog,
        scorers: dict[str, Scorer],
        config: HybridConfig,
        metadata: ArtifactMetadata,
    ) -> None:
        self.catalog = catalog
        self.scorers = scorers
        self.config = config
        self.metadata = metadata
        self.item_map = IdMap(ids=catalog.ids)
        self._genre_sets = [catalog.genre_set(i) for i in range(len(catalog.ids))]
        self.genre_names = {g.lower(): g for names in catalog.genres for g in names}

    # ---- building -----------------------------------------------------------------

    @classmethod
    def fit(
        cls,
        data: FitData,
        *,
        target: str,
        seed: int = 42,
        config: HybridConfig | None = None,
        settings: ModelSettings | None = None,
        data_hash: str = "",
    ) -> "Recommender":
        """Fit every model on ``data`` (which the split protocol has already limited).

        ``target`` ("validation" or "test") and ``data_hash`` are recorded as version
        information; they do not change the fit.
        """
        config = config or HybridConfig()
        settings = settings or ModelSettings()
        scorers: dict[str, Scorer] = {
            "popularity": PopularityScorer().fit(data),
            "bayesian_average": BayesianAverageScorer().fit(data),
            "random": RandomScorer(seed=seed).fit(data),
            "content": ContentScorer(weights=settings.content_weights).fit(data),
            "item_knn": ItemKNNScorer(
                neighbours=settings.neighbours,
                shrinkage=settings.shrinkage,
                min_support=settings.min_support,
            ).fit(data),
            "svd": SVDScorer(factors=settings.factors, seed=seed).fit(data),
        }
        knn, svd, bayes = (
            scorers["item_knn"],
            scorers["svd"],
            scorers["bayesian_average"],
        )
        assert isinstance(knn, ItemKNNScorer)
        assert isinstance(svd, SVDScorer)
        assert isinstance(bayes, BayesianAverageScorer)
        metadata = ArtifactMetadata(
            schema_version=SCHEMA_VERSION,
            created_utc=datetime.now(UTC).replace(microsecond=0).isoformat(),
            target=target,
            seed=seed,
            data_hash=data_hash,
            n_items=len(data.item_map),
            n_fit_users=int((np.diff(data.matrix.indptr) > 0).sum()),
            n_fit_ratings=int(data.matrix.nnz),
            n_fit_tags=int(len(data.tags)),
            libraries=library_versions(),
            config=_config_dict(config),
            model_params={
                "bayesian_average": {"prior_strength": bayes.prior_strength},
                "item_knn": {
                    "neighbours": knn.neighbours,
                    "shrinkage": knn.shrinkage,
                    "min_support": knn.min_support,
                },
                "svd": {"factors": svd.factors, "seed": svd.seed},
                "random": {"seed": seed},
                "content": {"use_tags": True},
            },
        )
        return cls(_catalog(data), scorers, config, metadata)

    # ---- the one public call ------------------------------------------------------

    def history(self, profile: UserProfile) -> History:
        """The profile's ratings as a history; refuses unknown movies, bad ratings."""
        ids = np.array(sorted(profile.ratings), dtype=np.int64)
        unknown = [int(i) for i in ids if int(i) not in self.item_map]
        if unknown:
            raise ValueError(f"movie ids not in the catalogue: {unknown[:5]}")
        ratings = np.array([profile.ratings[int(i)] for i in ids], dtype=np.float64)
        if ratings.size and (
            not np.isfinite(ratings).all()
            or ratings.min() < MIN_RATING
            or ratings.max() > MAX_RATING
        ):
            raise ValueError(f"ratings must be between {MIN_RATING} and {MAX_RATING}")
        return History(self.item_map.to_index(ids), ratings)

    def chosen_genres(self, profile: UserProfile) -> tuple[str, ...]:
        """The profile's favourite genres as sorted lower-case names; no unknowns."""
        wanted = sorted({g.strip().lower() for g in profile.genres if g.strip()})
        unknown = [g for g in wanted if g not in self.genre_names]
        if unknown:
            known = ", ".join(sorted(self.genre_names.values()))
            raise ValueError(f"unknown genres {unknown}; known genres: {known}")
        return tuple(wanted)

    def recommend(
        self, profile: UserProfile, strategy: str = "hybrid", k: int = 10
    ) -> RecommendationList:
        """Top ``k`` movies for ``profile`` by ``strategy``, never one already rated."""
        if strategy not in STRATEGIES:
            raise ValueError(f"unknown strategy {strategy!r}; use one of {STRATEGIES}")
        if k < 0:
            raise ValueError("k must not be negative")
        history = self.history(profile)
        genres = self.chosen_genres(profile)
        if strategy == "hybrid":
            return self._hybrid(history, genres, k)
        return self._single(strategy, history, k)

    # ---- hybrid -------------------------------------------------------------------

    def _candidates(self, history: History) -> IntArray:
        """Every catalogue position the user has not rated (D-023 candidate rule)."""
        keep = np.ones(len(self.item_map), dtype=bool)
        keep[history.items] = False
        return np.flatnonzero(keep)

    def _hybrid(
        self, history: History, genres: tuple[str, ...], k: int
    ) -> RecommendationList:
        branch = self.config.branch(len(history))
        popularity = self._popularity()
        notes: list[str] = []
        if branch == "no_ratings":
            return self._no_ratings(history, genres, k, popularity)
        if genres:
            notes.append("Favourite genres are only used when there are no ratings.")
        weights = self.config.weights_for(branch)
        candidates = self._candidates(history)
        raw = {name: self.scorers[name].score(history) for name in COMPONENTS}
        total, scaled = blend(raw, weights, candidates)
        chosen = rank_unseen(total, history.items, k)
        items = []
        for position in chosen.tolist():
            contributions = {
                name: weights[name] * float(scaled[name][position]) for name in scaled
            }
            order = sorted(
                contributions, key=lambda n: (-contributions[n], COMPONENTS.index(n))
            )
            # Explain with the method that contributed most and has real evidence;
            # popularity always has some, so it is the last resort.
            evidence, source = Evidence("no_evidence"), "popularity"
            for name in order:
                found = self._evidence(name, history, position)
                if found.kind != "no_evidence":
                    evidence, source = found, name
                    break
            if evidence.kind == "no_evidence":
                evidence = self._evidence("popularity", history, position)
            items.append(self._item(position, float(total[position]), evidence, source))
        return RecommendationList(
            "hybrid", branch, "hybrid blend (0 to 1)", tuple(items), tuple(notes)
        )

    def _no_ratings(
        self,
        history: History,
        genres: tuple[str, ...],
        k: int,
        popularity: PopularityScorer,
    ) -> RecommendationList:
        counts = popularity.score(history)
        if not genres:
            chosen = rank_unseen(counts, history.items, k)
            items = tuple(
                self._item(
                    p, float(counts[p]), popularity.evidence(history, p), "popularity"
                )
                for p in chosen.tolist()
            )
            note = "No ratings and no favourite genres: ranked by popularity alone."
            return RecommendationList(
                "hybrid", "no_ratings", "rating count", items, (note,)
            )
        everything = np.arange(len(self.item_map))
        popular = min_max_scale(counts, everything)
        match = genre_match(self._genre_sets, genres)
        total = (
            self.config.genre_weight * match + self.config.popularity_weight * popular
        )
        chosen = rank_unseen(total, history.items, k)
        items = tuple(
            self._item(
                p,
                float(total[p]),
                self._genre_evidence(popularity, history, p, genres),
                "popularity",
            )
            for p in chosen.tolist()
        )
        return RecommendationList(
            "hybrid", "no_ratings", "genre and popularity blend (0 to 1)", items
        )

    def _genre_evidence(
        self,
        popularity: PopularityScorer,
        history: History,
        position: int,
        chosen: tuple[str, ...],
    ) -> Evidence:
        """Popularity evidence naming only the chosen genres this movie really has.

        A movie that matches none of them is shown with plain popularity evidence, so
        the sentence never claims a genre match that did not happen.
        """
        shared = sorted(set(chosen) & self.catalog.genre_set(position))
        if not shared:
            return popularity.evidence(history, position)
        return Evidence(
            "genre_popularity",
            genres=tuple(self.genre_names[g] for g in shared),
            count=popularity.evidence(history, position).count,
        )

    # ---- single methods -----------------------------------------------------------

    def _single(self, strategy: str, history: History, k: int) -> RecommendationList:
        scorer = self.scorers[strategy]
        scores = scorer.score(history)
        chosen = rank_unseen(scores, history.items, k)
        kinds: dict[str, ScoreKind] = {
            "popularity": "rating count",
            "bayesian_average": "adjusted average rating",
            "random": "random draw",
            "content": "content similarity",
            "item_knn": "neighbour-weighted rating deviation",
            "svd": "latent-factor rating deviation",
        }
        items = []
        for position in chosen.tolist():
            value = float(scores[position])
            evidence = self._evidence(strategy, history, position)
            items.append(
                self._item(
                    position, value if np.isfinite(value) else None, evidence, strategy
                )
            )
        return RecommendationList(strategy, None, kinds[strategy], tuple(items))

    # ---- shared helpers -----------------------------------------------------------

    def _popularity(self) -> PopularityScorer:
        scorer = self.scorers["popularity"]
        assert isinstance(scorer, PopularityScorer)
        return scorer

    def _evidence(self, name: str, history: History, position: int) -> Evidence:
        """The named model's own evidence for recommending ``position``."""
        return self.scorers[name].evidence(history, position)

    def _item(
        self, position: int, score: float | None, evidence: Evidence, source: str
    ) -> Recommendation:
        return Recommendation(
            movie_id=int(self.catalog.ids[position]),
            title=self.catalog.titles[position],
            genres=self.catalog.genres[position],
            score=score,
            explanation=render(evidence, self.catalog.title_of),
            evidence=evidence,
            source=source,
        )


def _config_dict(config: HybridConfig) -> dict[str, Any]:
    return {
        "few_max": config.few_max,
        "genre_weight": config.genre_weight,
        "popularity_weight": config.popularity_weight,
        "few_weights": dict(config.few_weights),
        "many_weights": dict(config.many_weights),
    }


def profile_from_history(
    history: History, item_map: IdMap, genres: tuple[str, ...] = ()
) -> UserProfile:
    """A ``UserProfile`` from a ``History`` (for tests and protocol spot checks)."""
    ids = item_map.ids[history.items]
    return UserProfile(
        {int(i): float(r) for i, r in zip(ids, history.ratings, strict=True)}, genres
    )


__all__ = [
    "STRATEGIES",
    "TRUSTED_ARTIFACT_WARNING",
    "ArtifactMetadata",
    "Recommendation",
    "RecommendationList",
    "Recommender",
    "UserProfile",
    "profile_from_history",
]
