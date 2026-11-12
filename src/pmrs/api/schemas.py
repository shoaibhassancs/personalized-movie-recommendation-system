"""Request and response shapes. Responses list their fields explicitly, so a password
hash or a MovieLens user id can never be returned by accident."""

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

PASSWORD_MIN = 15
PASSWORD_MAX = 128
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _clean_email(value: str) -> str:
    email = value.strip().lower()
    if not _EMAIL.match(email):
        raise ValueError("not a valid email address")
    return email


class RegisterIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)
    display_name: str = Field(min_length=1, max_length=100)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return _clean_email(value)

    @field_validator("password")
    @classmethod
    def _password(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("password cannot be only spaces")
        return value  # never trimmed or truncated

    @field_validator("display_name")
    @classmethod
    def _name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("display name cannot be empty")
        return name


class LoginIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(min_length=1, max_length=PASSWORD_MAX)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return value.strip().lower()


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str
    genres: list[str]
    created_at: datetime


class ProfileIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)

    @field_validator("display_name")
    @classmethod
    def _name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("display name cannot be empty")
        return name


class GenresIn(BaseModel):
    genres: list[str] = Field(max_length=30)


class Poster(BaseModel):
    """A placeholder generated from the title: no image file, no outside service."""

    initials: str
    hue: int


class MovieOut(BaseModel):
    id: int
    title: str
    year: int | None
    genres: list[str]
    average_rating: float | None  # over ALL ratings in the database, incl. MovieLens
    rating_count: int
    poster: Poster


class MovieState(BaseModel):
    rating: float | None
    liked: bool
    disliked: bool
    watchlist: bool
    watched: bool
    viewed_at: datetime | None


class MovieDetail(MovieOut):
    tags: list[str]
    me: MovieState | None  # the caller's own state, only when logged in


class MoviePage(BaseModel):
    items: list[MovieOut]
    page: int
    page_size: int
    total: int


class RatingIn(BaseModel):
    rating: float

    @field_validator("rating")
    @classmethod
    def _half_stars(cls, value: float) -> float:
        if not 0.5 <= value <= 5 or not (value * 2).is_integer():
            raise ValueError("rating must be 0.5 to 5 in steps of 0.5")
        return value


class HistoryItem(BaseModel):
    movie: MovieOut
    state: MovieState
    last_activity: datetime


class HistoryPage(BaseModel):
    items: list[HistoryItem]
    page: int
    page_size: int
    total: int


# ---- recommendations, dashboard, analytics (chunk 4C) -------------------------


class RecommendationItem(BaseModel):
    movie: MovieOut
    score: float | None  # in the units of ``score_kind``; not comparable across methods
    explanation: str  # a fixed sentence built from the method's own evidence
    source: str  # the method whose evidence the sentence uses
    state: MovieState  # the caller's own rating and flags for this movie


class RecommendationsOut(BaseModel):
    strategy: str
    branch: str | None  # hybrid only: no_ratings, few_ratings or many_ratings
    branch_reason: str
    score_kind: str
    rating_count: int  # the caller's ratings used to build the profile
    items: list[RecommendationItem]
    notes: list[str]
    served_events_logged: int  # "shown" events: items served by the API, not seen
    model_notice: str


class TrendingItem(BaseModel):
    movie: MovieOut
    interactions: int


class TrendingOut(BaseModel):
    source: str  # "app_activity" or "dataset_latest_period"
    window_start: datetime
    window_end: datetime
    window_days: int
    note: str
    items: list[TrendingItem]


class DashboardOut(BaseModel):
    recommended: RecommendationsOut
    trending: TrendingOut
    popular: list[MovieOut]
    recent_releases: list[MovieOut]  # newest release years, not newest additions
    genres: list[str]
    watchlist: MoviePage
    activity: HistoryPage


class CountSplit(BaseModel):
    total: int
    movielens: int  # from the imported historical MovieLens users
    app: int  # from registered app users


class SummaryOut(BaseModel):
    movies: int
    users: CountSplit
    ratings: CountSplit
    interactions: dict[str, int]  # app interactions by kind (zeros included)
    recommendation_events: dict[str, int]  # shown / acted
    note: str


class RatingBucket(BaseModel):
    rating: float
    total: int
    movielens: int
    app: int


class RatingDistributionOut(BaseModel):
    buckets: list[RatingBucket]
    note: str


class StrategyEngagement(BaseModel):
    strategy: str
    served: int
    acted: int
    acted_per_served: float | None
    users: int


class EngagementOut(BaseModel):
    served: int
    acted: int
    users: int
    by_strategy: list[StrategyEngagement]
    note: str
