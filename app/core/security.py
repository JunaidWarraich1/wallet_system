"""
Security primitives used across the app.

Why these choices:
- Passwords are hashed with bcrypt (via passlib) — a slow, salted, adaptive hash
  purpose-built for passwords. We NEVER store or log plaintext passwords.
- JWT access tokens are short-lived (15 min default). Refresh tokens are longer
  lived but stored hashed in the DB so a stolen DB dump doesn't hand out valid
  refresh tokens directly (see repositories/refresh_token_repository.py).
- All tokens are signed (HS256) with a secret pulled from environment config,
  never hardcoded.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=settings.BCRYPT_ROUNDS)


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def validate_password_strength(password: str) -> tuple[bool, str | None]:
    """Basic password policy enforcement. Returns (is_valid, error_message)."""
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        return False, f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters long."
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter."
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter."
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one digit."
    if not any(not c.isalnum() for c in password):
        return False, "Password must contain at least one special character."
    return True, None


# ---------------------------------------------------------------------------
# JWT access tokens
# ---------------------------------------------------------------------------
def create_access_token(subject: str, role: str, extra_claims: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": expire,
        "jti": secrets.token_hex(16),  # unique token id, useful for revocation/audit
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Raises jose.JWTError if invalid/expired/tampered."""
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


# ---------------------------------------------------------------------------
# Refresh tokens (opaque random string, stored server-side as a hash)
# ---------------------------------------------------------------------------
def generate_refresh_token() -> str:
    return secrets.token_urlsafe(64)


def hash_refresh_token(token: str) -> str:
    # SHA-256 is fine here (not a password, already high-entropy random value);
    # we just need a fast, deterministic lookup hash so the raw token is never
    # stored at rest.
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Idempotency key hashing (for safe indexed storage/lookup)
# ---------------------------------------------------------------------------
def normalize_idempotency_key(raw_key: str) -> str:
    return raw_key.strip()
