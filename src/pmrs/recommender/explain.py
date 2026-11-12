"""Step 11: evidence behind a recommendation, and the fixed sentences built from it.

One interface, used everywhere: each model's ``evidence(history, item)`` returns an
``Evidence`` (plain facts: which of the user's rated movies, which genres or tags, how
many people rated it). ``render`` turns evidence into a sentence using a fixed template,
so an explanation can only mention things that were actually in the evidence. The
``Recommender`` calls ``render`` and keeps both the evidence and the sentence.

Explanations describe what the mechanism did; they are not proof of why the user would
like a movie, and the SVD and hybrid explanations are deliberately modest.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt

MAX_TAGS_SHOWN = 5  # a sentence naming 17 shared tags is true but unreadable

Kind = Literal[
    "content",
    "neighbours",
    "taste_pattern",
    "popularity",
    "overall_rating",
    "genre_popularity",
    "random",
    "no_evidence",
]


@dataclass(frozen=True)
class Evidence:
    """Facts behind one recommended movie. Movie IDs are raw MovieLens IDs."""

    kind: Kind
    movies: tuple[int, ...] = ()  # the user's own rated movies the reason points to
    ratings: tuple[float, ...] = ()  # the user's ratings of those movies
    genres: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    value: float = 0.0  # similarity, or a weighted average rating
    count: int = 0  # number of raters, or number of supporting neighbours
    # content evidence only: the user's own mean rating, and whether the movie it points
    # to was really rated above that mean (False: the "nothing above average" fallback)
    average: float | None = None
    above_average: bool = True


@dataclass(frozen=True)
class Explanation:
    source: str  # the model (or ladder branch) the evidence came from
    evidence: Evidence
    text: str


class Catalog:
    """Display facts for every catalogue movie, in item-position order."""

    def __init__(
        self,
        ids: npt.NDArray[np.int64],
        titles: Sequence[str],
        genres: Sequence[Sequence[str]],
    ) -> None:
        if not len(ids) == len(titles) == len(genres):
            raise ValueError("ids, titles and genres must have the same length")
        self.ids = ids
        self.titles = tuple(titles)
        self.genres = tuple(tuple(g) for g in genres)
        self._position = {int(movie_id): n for n, movie_id in enumerate(ids.tolist())}

    def title_of(self, movie_id: int) -> str:
        return self.titles[self._position[movie_id]]

    def genre_set(self, position: int) -> frozenset[str]:
        """Lower-case genre names of the movie at ``position``."""
        return frozenset(g.lower() for g in self.genres[position])


def _join(items: Sequence[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _average_text(average: float, rating: float) -> str:
    """The user's mean with enough digits to read as different from ``rating``.

    A mean of 2.4967 printed to two places is "2.50", and "rated 2.5, above your
    average of 2.50" contradicts itself. So add digits until the printed mean is
    visibly below the rating it is compared with (at least two places, at most six).
    """
    for digits in range(2, 7):
        text = f"{average:.{digits}f}"
        if float(text) < rating:
            return text
    return text


def _rated(
    evidence: Evidence, title_of: Callable[[int], str], limit: int | None = None
) -> list[str]:
    pairs = list(zip(evidence.movies, evidence.ratings, strict=False))[:limit]
    return [f"'{title_of(m)}' ({r:g})" for m, r in pairs]


def render(evidence: Evidence, title_of: Callable[[int], str]) -> str:
    """The fixed sentence for ``evidence``; ``title_of`` maps a movie id to a title."""
    kind = evidence.kind
    if kind == "content":
        movie = _rated(evidence, title_of, 1)[0]
        shared = []
        if evidence.genres:
            shared.append(f"the genres {_join(evidence.genres)}")
        if evidence.tags:  # all are shared; only the first few are worth printing
            shared.append(f"the tags {_join(evidence.tags[:MAX_TAGS_SHOWN])}")
        average = evidence.average
        rated = evidence.ratings[0]
        if average is None:  # no average known: say only what was rated
            if shared:
                return f"Because you rated {movie} and it shares {_join(shared)}."
            return f"It is similar in title or era to {movie}, which you rated."
        if evidence.above_average:
            # the movie only counts as a "liked" one because it beats the user's own
            # average, so say so: a 2.5 from a harsh rater is a relatively good rating
            mean = _average_text(average, rated)
            above = f"{movie}, which is above your own average of {mean}"
            if shared:
                return f"Because you rated {above}, and it shares {_join(shared)}."
            return f"It is similar in title or era to {above}."
        # fallback: nothing was above average, so no movie here is a "liked" one
        caveat = (
            f"None of your ratings is above your own average of {average:.2f}, so "
            "this is just the closest of the movies you rated."
        )
        if shared:
            return f"It shares {_join(shared)} with {movie}, which you rated. {caveat}"
        return f"It is similar in title or era to {movie}, which you rated. {caveat}"
    if kind == "neighbours":
        movies = _join(_rated(evidence, title_of))
        return (
            f"Other viewers' ratings of this movie tend to move together with their "
            f"ratings of {movies}, which you rated."
        )
    if kind == "taste_pattern":
        text = "It fits your overall rating pattern (a statistical match)"
        if evidence.movies:
            text += f", and is closest to {_rated(evidence, title_of, 1)[0]}"
        return text + "."
    if kind == "popularity":
        return (
            f"Popular choice: {evidence.count} people rated it. This is not based on "
            "your taste."
        )
    if kind == "overall_rating":
        return (
            f"Highly rated overall (weighted average {evidence.value:.1f} from "
            f"{evidence.count} ratings). This is not based on your taste."
        )
    if kind == "genre_popularity":
        return (
            f"Popular in the genres you chose ({_join(evidence.genres)}): "
            f"{evidence.count} people rated it. This is not based on any ratings "
            "from you."
        )
    if kind == "random":
        return "Random pick, not based on your taste."
    return (
        "There is nothing to learn from for this method, so this is a default "
        "ordering, not a recommendation."
    )
