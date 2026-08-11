import time
import uuid
from collections import defaultdict, deque

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError, AuthorizationError, RateLimitError
from app.core.security import decode_token
from app.database import get_db
from app.models.user import User, UserRole, UserStatus
from app.repositories.user_repository import UserRepository

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise AuthenticationError("Not authenticated. Provide a Bearer token.")

    try:
        payload = decode_token(credentials.credentials)
    except JWTError:
        raise AuthenticationError("Invalid or expired token.")

    if payload.get("type") != "access":
        raise AuthenticationError("Invalid token type.")

    user_id = payload.get("sub")
    if not user_id:
        raise AuthenticationError("Invalid token.")

    user = UserRepository(db).get_by_id(uuid.UUID(user_id))
    if user is None or user.status != UserStatus.ACTIVE:
        raise AuthenticationError("User not found or inactive.")

    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise AuthorizationError("This action requires administrator privileges.")
    return current_user


def require_customer(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.CUSTOMER:
        raise AuthorizationError("This action is only available to customer accounts.")
    return current_user


# ---------------------------------------------------------------------------
# Simple in-memory sliding-window rate limiter.
#
# NOTE: this is process-local, which is fine for a single-instance deployment
# or for this assignment. For a real multi-instance production deployment,
# back this with Redis (e.g. redis + a sliding-window or token-bucket script)
# so limits are enforced consistently across all app instances.
# ---------------------------------------------------------------------------
_request_log: dict[str, deque] = defaultdict(deque)


def _check_rate_limit(key: str, limit: int, window_seconds: int = 60) -> None:
    now = time.time()
    log = _request_log[key]
    while log and log[0] < now - window_seconds:
        log.popleft()
    if len(log) >= limit:
        raise RateLimitError("Too many requests. Please slow down and try again shortly.")
    log.append(now)


def rate_limit_default(request: Request, current_user: User = Depends(get_current_user)) -> None:
    from app.core.config import settings

    _check_rate_limit(f"default:{current_user.id}", settings.RATE_LIMIT_PER_MINUTE)


def rate_limit_transfer(request: Request, current_user: User = Depends(get_current_user)) -> None:
    from app.core.config import settings

    _check_rate_limit(f"transfer:{current_user.id}", settings.TRANSFER_RATE_LIMIT_PER_MINUTE)


def rate_limit_by_ip(request: Request, limit: int = 10, window_seconds: int = 60) -> None:
    """For unauthenticated endpoints (login, register) where we can't key on
    a user id yet — throttles by client IP to slow down credential stuffing
    and registration-spam attacks."""
    ip = get_client_ip(request) or "unknown"
    _check_rate_limit(f"ip:{request.url.path}:{ip}", limit, window_seconds)


def get_client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None
