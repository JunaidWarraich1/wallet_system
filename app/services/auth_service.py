from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AccountLockedError, AuthenticationError, ConflictError
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.auth import RefreshToken
from app.models.user import User, UserRole, UserStatus
from app.repositories.auth_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.users = UserRepository(db)
        self.refresh_tokens = RefreshTokenRepository(db)

    def register(self, name: str, email: str, password: str) -> User:
        email = email.lower().strip()
        if self.users.get_by_email(email) is not None:
            # Deliberately generic message — do not reveal whether the email
            # exists via a different error for "already registered" vs other
            # failures, to avoid user-enumeration in stricter deployments.
            # (Kept slightly specific here for UX; swap to a generic message
            # if enumeration resistance is required by policy.)
            raise ConflictError("An account with this email already exists.")

        user = User(
            name=name,
            email=email,
            password_hash=hash_password(password),
            role=UserRole.CUSTOMER,
            status=UserStatus.ACTIVE,
        )
        self.users.create(user)
        self.db.commit()
        return user

    def authenticate(self, email: str, password: str) -> User:
        email = email.lower().strip()
        user = self.users.get_by_email(email)

        # Constant-shape response: whether the user exists or not, we still
        # run a password verification against a dummy hash to avoid leaking
        # user existence via response timing.
        if user is None:
            verify_password(password, "$2b$12$" + "0" * 53)
            raise AuthenticationError("Invalid email or password.")

        if user.locked_until and user.locked_until > datetime.now(timezone.utc):
            raise AccountLockedError(
                f"Account is temporarily locked due to repeated failed login attempts. "
                f"Try again after {user.locked_until.isoformat()}."
            )

        if user.status != UserStatus.ACTIVE:
            raise AuthenticationError("This account is not active.")

        if not verify_password(password, user.password_hash):
            self.users.record_failed_login(user)
            if user.failed_login_attempts >= settings.MAX_FAILED_LOGIN_ATTEMPTS:
                lock_until = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCOUNT_LOCKOUT_MINUTES)
                self.users.lock_account(user, lock_until)
                self.db.commit()
                raise AccountLockedError(
                    f"Too many failed attempts. Account locked for {settings.ACCOUNT_LOCKOUT_MINUTES} minutes."
                )
            self.db.commit()
            raise AuthenticationError("Invalid email or password.")

        self.users.reset_failed_logins(user)
        self.db.commit()
        return user

    def issue_tokens(self, user: User) -> tuple[str, str]:
        access_token = create_access_token(subject=str(user.id), role=user.role.value)
        raw_refresh = generate_refresh_token()
        refresh_record = RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
        self.refresh_tokens.create(refresh_record)
        self.db.commit()
        return access_token, raw_refresh

    def refresh_access_token(self, raw_refresh_token: str) -> tuple[str, str]:
        token_hash = hash_refresh_token(raw_refresh_token)
        record = self.refresh_tokens.get_by_hash(token_hash)

        if record is None or record.revoked or record.expires_at < datetime.now(timezone.utc):
            raise AuthenticationError("Invalid or expired refresh token.")

        user = self.users.get_by_id(record.user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            raise AuthenticationError("Invalid or expired refresh token.")

        # Rotate: revoke the used refresh token and issue a brand new pair.
        # This limits the blast radius if a refresh token is ever stolen —
        # it can only be used once before rotation invalidates it.
        self.refresh_tokens.revoke(record)
        self.db.commit()
        return self.issue_tokens(user)

    def logout(self, raw_refresh_token: str) -> None:
        token_hash = hash_refresh_token(raw_refresh_token)
        record = self.refresh_tokens.get_by_hash(token_hash)
        if record is not None:
            self.refresh_tokens.revoke(record)
            self.db.commit()
