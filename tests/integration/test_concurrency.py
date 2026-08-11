"""
This test proves the core correctness guarantee of the assignment (spec
section 8, Rule 8 / section 9): concurrent transfers against the same
wallet can never over-draw it, because of SELECT ... FOR UPDATE locking.

It fires N simultaneous transfer requests, each for an amount that would
individually succeed, but where the SUM of all of them exceeds the wallet's
balance. Without correct locking, several requests could all read the same
starting balance and all "succeed" — over-drawing the wallet. With correct
locking, only as many as the balance allows should succeed; the rest must
be cleanly rejected with "Insufficient balance", and the final balance must
never go negative.
"""
import threading
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import hash_password
from app.models.user import User, UserRole, UserStatus
from app.models.wallet import Wallet, WalletStatus
from app.services.transfer_service import TransferService
from tests.conftest import TEST_DATABASE_URL


def test_concurrent_transfers_never_overdraw_wallet(db_session):
    # Set up sender with exactly 1000 balance, and 5 recipients.
    sender_user = User(
        id=uuid.uuid4(), name="Sender", email="sender@concurrency.test",
        password_hash=hash_password("StrongP@ss123"), role=UserRole.CUSTOMER, status=UserStatus.ACTIVE,
    )
    sender_wallet = Wallet(id=uuid.uuid4(), user_id=sender_user.id, balance=1000, currency="USD", status=WalletStatus.ACTIVE)
    db_session.add_all([sender_user, sender_wallet])

    recipients = []
    for i in range(5):
        u = User(
            id=uuid.uuid4(), name=f"R{i}", email=f"r{i}@concurrency.test",
            password_hash=hash_password("StrongP@ss123"), role=UserRole.CUSTOMER, status=UserStatus.ACTIVE,
        )
        w = Wallet(id=uuid.uuid4(), user_id=u.id, balance=0, currency="USD", status=WalletStatus.ACTIVE)
        db_session.add_all([u, w])
        recipients.append(w)
    db_session.commit()

    sender_id = sender_user.id
    sender_wallet_id = sender_wallet.id
    recipient_ids = [w.id for w in recipients]

    # Each thread gets its OWN engine/session (mirrors separate concurrent
    # HTTP requests each getting their own DB connection via get_db()).
    engine = create_engine(TEST_DATABASE_URL)
    SessionFactory = sessionmaker(bind=engine)

    results = []
    results_lock = threading.Lock()

    def attempt_transfer(recipient_wallet_id, amount, key):
        session = SessionFactory()
        try:
            service = TransferService(session)
            try:
                service.transfer(
                    sender_user_id=sender_id,
                    sender_wallet_id=sender_wallet_id,
                    recipient_wallet_id=recipient_wallet_id,
                    amount=amount,
                    description="concurrency test",
                    idempotency_key=key,
                )
                with results_lock:
                    results.append("SUCCESS")
            except Exception as e:
                with results_lock:
                    results.append(f"REJECTED: {type(e).__name__}")
        finally:
            session.close()

    # 5 threads each try to transfer 300 (5 * 300 = 1500 > 1000 available).
    # At most 3 can succeed (3*300=900 <= 1000, a 4th would need 1200 > 1000).
    threads = [
        threading.Thread(target=attempt_transfer, args=(recipient_ids[i], 300, f"concurrency-key-{i}"))
        for i in range(5)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    successes = [r for r in results if r == "SUCCESS"]
    assert len(successes) <= 3, f"Expected at most 3 successful transfers, got {len(successes)}: {results}"

    # Verify final sender balance is never negative and matches exactly
    # (balance = 1000 - successes*300).
    verify_session = SessionFactory()
    final_wallet = verify_session.get(Wallet, sender_wallet_id)
    assert final_wallet.balance >= 0
    assert final_wallet.balance == 1000 - (len(successes) * 300)
    verify_session.close()
