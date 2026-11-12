"""Password hashing (Argon2id) and access tokens (HS256 JWT).

Passwords are never trimmed, normalised or truncated: what was typed is what is hashed.
A token carries only the user's id (``sub``), issue time and expiry. There is no refresh
token and no server-side logout: logging out means the client drops the token.
"""

from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

ALGORITHM = "HS256"
_hasher = PasswordHasher()  # argon2id with the library's current defaults
# a real hash to check when the email is unknown, so timing does not reveal it
_DUMMY_HASH = _hasher.hash("not-a-real-password-used-only-for-timing")


class InvalidTokenError(Exception):
    """The token is missing a claim, expired, tampered with or signed otherwise."""


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    """True only for a match. With no stored hash it still does the same work."""
    try:
        return _hasher.verify(stored_hash or _DUMMY_HASH, password) and bool(
            stored_hash
        )
    except (VerificationError, InvalidHashError):
        return False


def create_token(user_id: int, secret: str, minutes: int) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(claims, secret, algorithm=ALGORITHM)


def read_token(token: str, secret: str) -> int:
    """The user id in a valid token; raises ``InvalidTokenError`` for anything else."""
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],  # a token claiming another algorithm is refused
            options={"require": ["exp", "iat", "sub"]},
        )
        return int(claims["sub"])
    except (jwt.PyJWTError, ValueError, KeyError) as error:
        raise InvalidTokenError("invalid or expired token") from error
