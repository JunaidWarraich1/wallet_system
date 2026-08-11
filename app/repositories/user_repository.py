import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    """
    Pure data access. No business rules live here — only reads/writes.
    Uses SQLAlchemy ORM queries exclusively (parameterized by construction),
    so this layer is not susceptible to SQL injection.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self.db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email.lower())
        return self.db.execute(stmt).scalar_one_or_none()

    def create(self, user: User) -> User:
        self.db.add(user)
        self.db.flush()
        return user

    def list_all(self, page: int = 1, page_size: int = 20) -> tuple[list[User], int]:
        total = self.db.execute(select(User)).scalars().all()
        stmt = select(User).order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        items = self.db.execute(stmt).scalars().all()
        return list(items), len(total)

    def record_failed_login(self, user: User) -> None:
        user.failed_login_attempts += 1
        self.db.flush()

    def reset_failed_logins(self, user: User) -> None:
        user.failed_login_attempts = 0
        user.locked_until = None
        self.db.flush()

    def lock_account(self, user: User, until: datetime) -> None:
        user.locked_until = until
        self.db.flush()
