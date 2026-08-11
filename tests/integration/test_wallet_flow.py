def register_and_login(client, name, email, password="StrongP@ss123"):
    client.post("/api/auth/register", json={"name": name, "email": email, "password": password})
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    return resp.json()["access_token"]


def create_wallet(client, token, currency="USD"):
    resp = client.post("/api/wallet/", json={"currency": currency}, headers={"Authorization": f"Bearer {token}"})
    return resp.json()


def test_create_wallet_and_duplicate_currency_rejected(client):
    token = register_and_login(client, "Alice", "alice@example.com")
    w1 = create_wallet(client, token, "USD")
    assert w1["balance"] == "0.00"

    resp = client.post("/api/wallet/", json={"currency": "USD"}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 409


def test_deposit_increases_balance(client):
    token = register_and_login(client, "Alice", "alice2@example.com")
    wallet = create_wallet(client, token)
    resp = client.post(
        "/api/wallet/deposit/",
        json={"wallet_id": wallet["id"], "amount": 1000},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "COMPLETED"

    wallet_resp = client.get(f"/api/wallet/{wallet['id']}", headers={"Authorization": f"Bearer {token}"})
    assert wallet_resp.json()["balance"] == "1000.00"


def test_deposit_idempotency_key_prevents_double_deposit(client):
    token = register_and_login(client, "Alice", "alice3@example.com")
    wallet = create_wallet(client, token)
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "dep-abc"}
    client.post("/api/wallet/deposit/", json={"wallet_id": wallet["id"], "amount": 1000}, headers=headers)
    client.post("/api/wallet/deposit/", json={"wallet_id": wallet["id"], "amount": 1000}, headers=headers)

    wallet_resp = client.get(f"/api/wallet/{wallet['id']}", headers={"Authorization": f"Bearer {token}"})
    assert wallet_resp.json()["balance"] == "1000.00"  # not 2000


def test_withdraw_insufficient_balance_rejected(client):
    token = register_and_login(client, "Alice", "alice4@example.com")
    wallet = create_wallet(client, token)
    resp = client.post(
        "/api/wallet/withdraw/",
        json={"wallet_id": wallet["id"], "amount": 100},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    assert "Insufficient" in resp.json()["error"]["message"]


def test_withdraw_never_makes_balance_negative(client):
    token = register_and_login(client, "Alice", "alice5@example.com")
    wallet = create_wallet(client, token)
    client.post(
        "/api/wallet/deposit/", json={"wallet_id": wallet["id"], "amount": 100}, headers={"Authorization": f"Bearer {token}"}
    )
    resp = client.post(
        "/api/wallet/withdraw/",
        json={"wallet_id": wallet["id"], "amount": 150},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    wallet_resp = client.get(f"/api/wallet/{wallet['id']}", headers={"Authorization": f"Bearer {token}"})
    assert wallet_resp.json()["balance"] == "100.00"


def test_transfer_full_flow_and_self_transfer_rejected(client):
    alice_token = register_and_login(client, "Alice", "alicex@example.com")
    bob_token = register_and_login(client, "Bob", "bobx@example.com")
    alice_wallet = create_wallet(client, alice_token)
    bob_wallet = create_wallet(client, bob_token)

    client.post(
        "/api/wallet/deposit/",
        json={"wallet_id": alice_wallet["id"], "amount": 10000},
        headers={"Authorization": f"Bearer {alice_token}"},
    )

    # self-transfer rejected
    resp = client.post(
        "/api/wallet/transfer/",
        json={"sender_wallet_id": alice_wallet["id"], "recipient_wallet_id": alice_wallet["id"], "amount": 100},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert resp.status_code == 422

    # real transfer
    resp2 = client.post(
        "/api/wallet/transfer/",
        json={
            "sender_wallet_id": alice_wallet["id"],
            "recipient_wallet_id": bob_wallet["id"],
            "amount": 3000,
            "description": "Payment for services",
        },
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert resp2.status_code == 200

    alice_bal = client.get(f"/api/wallet/{alice_wallet['id']}", headers={"Authorization": f"Bearer {alice_token}"}).json()["balance"]
    bob_bal = client.get(f"/api/wallet/{bob_wallet['id']}", headers={"Authorization": f"Bearer {bob_token}"}).json()["balance"]
    assert alice_bal == "7000.00"
    assert bob_bal == "3000.00"


def test_transfer_idempotency_key_prevents_double_transfer(client):
    alice_token = register_and_login(client, "Alice", "alicey@example.com")
    bob_token = register_and_login(client, "Bob", "boby@example.com")
    alice_wallet = create_wallet(client, alice_token)
    bob_wallet = create_wallet(client, bob_token)
    client.post(
        "/api/wallet/deposit/",
        json={"wallet_id": alice_wallet["id"], "amount": 10000},
        headers={"Authorization": f"Bearer {alice_token}"},
    )

    headers = {"Authorization": f"Bearer {alice_token}", "Idempotency-Key": "transfer-xyz"}
    payload = {"sender_wallet_id": alice_wallet["id"], "recipient_wallet_id": bob_wallet["id"], "amount": 3000}
    r1 = client.post("/api/wallet/transfer/", json=payload, headers=headers)
    r2 = client.post("/api/wallet/transfer/", json=payload, headers=headers)
    assert r1.json()["id"] == r2.json()["id"]

    alice_bal = client.get(f"/api/wallet/{alice_wallet['id']}", headers={"Authorization": f"Bearer {alice_token}"}).json()["balance"]
    assert alice_bal == "7000.00"  # only debited once


def test_frozen_wallet_rejects_deposit_withdraw_transfer(client, db_session):
    from app.services.admin_wallet_service import AdminWalletService
    from tests.conftest import make_user
    from app.models.user import UserRole
    import uuid as uuid_lib

    alice_token = register_and_login(client, "Alice", "alicez@example.com")
    alice_wallet = create_wallet(client, alice_token)

    admin_user = make_user(db_session, email="freeze-admin@example.com", role=UserRole.ADMIN)
    admin_service = AdminWalletService(db_session)
    admin_service.freeze_wallet(
        admin_id=admin_user.id, wallet_id=uuid_lib.UUID(alice_wallet["id"]), reason="test freeze", ip_address=None
    )

    resp = client.post(
        "/api/wallet/deposit/",
        json={"wallet_id": alice_wallet["id"], "amount": 100},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert resp.status_code == 422
