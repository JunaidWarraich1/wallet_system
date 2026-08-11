from app.models.user import UserRole
from tests.conftest import make_user


def register_and_login(client, email="alice@example.com", password="StrongP@ss123"):
    client.post("/api/auth/register", json={"name": "Alice", "email": email, "password": password})
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    return resp.json()["access_token"], resp.json()["refresh_token"]


def test_register_rejects_weak_password(client):
    resp = client.post(
        "/api/auth/register", json={"name": "Alice", "email": "alice@example.com", "password": "weak"}
    )
    assert resp.status_code == 422


def test_register_rejects_duplicate_email(client):
    client.post("/api/auth/register", json={"name": "Alice A", "email": "dup@example.com", "password": "StrongP@ss123"})
    resp = client.post(
        "/api/auth/register", json={"name": "Bob B", "email": "dup@example.com", "password": "StrongP@ss123"}
    )
    assert resp.status_code == 409


def test_login_success_issues_tokens(client):
    access, refresh = register_and_login(client)
    assert access
    assert refresh


def test_login_wrong_password_rejected(client):
    client.post("/api/auth/register", json={"name": "Alice A", "email": "a@example.com", "password": "StrongP@ss123"})
    resp = client.post("/api/auth/login", json={"email": "a@example.com", "password": "WrongPass1!"})
    assert resp.status_code == 401


def test_account_locks_after_max_failed_attempts(client):
    client.post("/api/auth/register", json={"name": "Alice A", "email": "lock@example.com", "password": "StrongP@ss123"})
    for _ in range(5):
        client.post("/api/auth/login", json={"email": "lock@example.com", "password": "WrongPass1!"})
    resp = client.post("/api/auth/login", json={"email": "lock@example.com", "password": "StrongP@ss123"})
    assert resp.status_code == 423


def test_refresh_token_rotation(client):
    _, refresh = register_and_login(client)
    resp = client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 200
    new_refresh = resp.json()["refresh_token"]
    assert new_refresh != refresh

    # Old refresh token must now be invalid (rotation)
    resp2 = client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert resp2.status_code == 401


def test_unauthenticated_request_rejected(client):
    resp = client.get("/api/wallet/")
    assert resp.status_code == 401


def test_customer_cannot_access_admin_routes(client):
    access, _ = register_and_login(client)
    resp = client.get("/api/admin/users", headers={"Authorization": f"Bearer {access}"})
    assert resp.status_code == 403


def test_admin_can_access_admin_routes(client, db_session):
    admin = make_user(db_session, email="admin@example.com", role=UserRole.ADMIN)
    resp = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "StrongP@ss123"})
    access = resp.json()["access_token"]
    resp2 = client.get("/api/admin/users", headers={"Authorization": f"Bearer {access}"})
    assert resp2.status_code == 200
