"""POST /auth/register and POST /auth/login."""

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from pmrs.api.deps import SessionDep
from pmrs.api.schemas import LoginIn, RegisterIn, TokenOut, UserOut
from pmrs.api.security import create_token, hash_password, verify_password
from pmrs.db.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


def user_out(user: User, genres: list[str]) -> UserOut:
    assert user.email is not None  # registered users always have one (DB check)
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        genres=genres,
        created_at=user.created_at,
    )


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserOut)
def register(body: RegisterIn, session: SessionDep) -> UserOut:
    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        is_historical=False,
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "email already registered"
        ) from None
    session.refresh(user)
    return user_out(user, [])


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, session: SessionDep, request: Request) -> TokenOut:
    # only registered users can be found: a historical user has no email at all
    user = session.execute(
        select(User).where(User.email == body.email, User.is_historical.is_(False))
    ).scalar_one_or_none()
    ok = verify_password(user.password_hash if user else None, body.password)
    if user is None or not ok:  # same answer and same work for both failures
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    minutes = request.app.state.token_minutes
    token = create_token(user.id, request.app.state.jwt_secret, minutes)
    return TokenOut(access_token=token, expires_in=minutes * 60)
