"""Shared request dependencies: database session, current user."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from pmrs.api.security import InvalidTokenError, read_token
from pmrs.db.models import User

_bearer = HTTPBearer(auto_error=False)
_UNAUTHORIZED = HTTPException(
    status.HTTP_401_UNAUTHORIZED,
    "invalid or missing credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


def _user_from(credentials: HTTPAuthorizationCredentials, request: Request) -> User:
    try:
        user_id = read_token(credentials.credentials, request.app.state.jwt_secret)
    except InvalidTokenError:
        raise _UNAUTHORIZED from None
    with Session(request.app.state.engine) as session:
        user = session.get(User, user_id)
        # a token can never act as a MovieLens (historical) user, even if forged
        if user is None or user.is_historical:
            raise _UNAUTHORIZED
        session.expunge(user)
        return user


def current_user(request: Request, credentials: Credentials) -> User:
    if credentials is None:
        raise _UNAUTHORIZED
    return _user_from(credentials, request)


def optional_user(request: Request, credentials: Credentials) -> User | None:
    """No header: anonymous. A header that is present must be valid."""
    if credentials is None:
        return None
    return _user_from(credentials, request)


CurrentUser = Annotated[User, Depends(current_user)]
OptionalUser = Annotated[User | None, Depends(optional_user)]
