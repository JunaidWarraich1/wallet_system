import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import hash_password
from app.database import Base, get_db
from app.main import app
from app.models.user import User, UserRole, UserStatus

TEST_DATABASE_URL = settings.DATABASE_URL.replace("/wallet_db", "/wallet_test_db")

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        conn.execute(text("CREATE SEQUENCE IF NOT EXISTS transaction_reference_seq START WITH 1 INCREMENT BY 1"))
        conn.commit()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def clean_tables():
    """Truncate all tables between tests so each test starts from a clean slate."""
    yield
    with engine.connect() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
        conn.commit()


@pytest.fixture
def db_session():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session):
    from app.api.deps import _request_log

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    _request_log.clear()  # in-memory rate limiter is process-global; reset between tests
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    _request_log.clear()


def make_user(db_session, email="user@example.com", role=UserRole.CUSTOMER, password="StrongP@ss123") -> User:
    user = User(
        id=uuid.uuid4(),
        name="Test User",
        email=email,
        password_hash=hash_password(password),
        role=role,
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user
