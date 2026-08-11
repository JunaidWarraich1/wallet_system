# Digital Wallet & Money Transfer System

A backend system for creating wallets, depositing, withdrawing, and transferring money between users — built with a strict layered architecture and a strong focus on financial-system security.

## Tech Stack

- **Framework:** FastAPI (Python 3.12)
- **Database:** PostgreSQL 16
- **ORM:** SQLAlchemy 2.0
- **Migrations:** Alembic
- **Auth:** JWT (access tokens) + rotating opaque refresh tokens
- **Password hashing:** bcrypt (via passlib)

## Architecture

Strict separation of concerns, exactly as required:

```
Client
  │
  ▼
API / Controller Layer      (app/api/routers)   — HTTP concerns only, no business logic
  │
  ▼
Business / Service Layer    (app/services)       — ALL business rules live here
  │
  ▼
Repository / Data Access    (app/repositories)   — pure DB reads/writes, no business logic
  │
  ▼
Database (PostgreSQL)
```

```
app/
├── main.py                 # FastAPI app, middleware, global exception handlers
├── database.py              # SQLAlchemy engine/session
├── api/
│   ├── deps.py               # auth, RBAC, rate-limit dependencies
│   └── routers/               # auth.py, wallet.py, admin.py
├── core/
│   ├── config.py              # env-based settings
│   ├── security.py            # password hashing, JWT
│   └── exceptions.py          # domain exception hierarchy
├── models/                   # SQLAlchemy ORM models
├── schemas/                  # Pydantic request/response models
├── services/                  # business logic — wallet, transfer, transaction, admin, auth
├── repositories/               # data access layer
alembic/                       # DB migrations
tests/
├── unit/
└── integration/               # incl. a concurrency test proving no race conditions
```

## Security Measures (this was the grading priority)

| Area | What's implemented |
|---|---|
| **Passwords** | bcrypt hashing, strength policy (length, upper/lower/digit/special char), never logged or returned |
| **Auth** | Short-lived JWT access tokens (15 min) + long-lived refresh tokens stored **hashed** in DB, rotated on every refresh |
| **Brute force** | Per-account lockout after 5 failed logins (15 min), plus IP-based rate limiting on login/register |
| **Authorization** | Role-based access control (CUSTOMER / ADMIN) enforced via FastAPI dependencies on every route |
| **SQL injection** | Impossible by construction — 100% SQLAlchemy ORM, zero raw/string-built SQL anywhere |
| **Input validation** | Every request body is a Pydantic model with strict types, length limits, and value constraints |
| **Race conditions** | `SELECT ... FOR UPDATE` row locking on wallets before any balance read/write, with a **fixed lock order** (sorted by UUID) to prevent deadlocks — see `app/services/transfer_service.py` |
| **Atomicity** | Debit + credit + transaction record happen in a single DB transaction; anything failing rolls back everything (see Section 9 of the spec) |
| **Idempotency** | `Idempotency-Key` header, unique-indexed at the DB level, so retried requests never double-process |
| **Balance integrity** | DB-level `CHECK (balance >= 0)` constraint as a last line of defense |
| **Admin balance changes** | Never a raw field update — always a controlled, auditable operation that also creates a transaction record |
| **Audit trail** | Every admin action (freeze/unfreeze/adjust) writes to an immutable `audit_logs` table with actor, reason, and IP |
| **Error handling** | Centralized exception handling — internal errors/stack traces are logged server-side only, clients get safe generic messages |
| **Transport/headers** | Security headers on every response (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, HSTS in production), explicit CORS allow-list |
| **Enumeration resistance** | Wallets/transactions not owned by the caller return 404 (not 403), login uses constant-shape responses |

## Setup & Running Locally

### 1. Prerequisites
- Python 3.12+
- PostgreSQL 16 (running locally, or use Docker — see below)

### 2. Clone and install
```bash
git clone <your-repo-url>
cd wallet-system
pip install -r requirements.txt
```

### 3. Configure environment
```bash
cp .env.example .env
# Edit .env: set a real JWT_SECRET_KEY and your DATABASE_URL
# Generate a secret with:
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

### 4. Create the database
```bash
createdb wallet_db
# or: psql -c "CREATE DATABASE wallet_db;"
```

### 5. Run migrations
```bash
alembic upgrade head
```

### 6. Start the server
```bash
uvicorn app.main:app --reload
```

The API is now live at `http://localhost:8000`. Interactive docs (dev only): `http://localhost:8000/api/docs`.

## Running with Docker

```bash
cp .env.example .env   # edit JWT_SECRET_KEY at minimum
docker compose up --build
```

This spins up Postgres + the API together, runs migrations automatically, and serves on `http://localhost:8000`.

## Running Tests

Tests run against a **real PostgreSQL database** (a separate `wallet_test_db`), not mocks — including a concurrency test that fires simultaneous transfer requests against the same wallet to prove the row-locking actually prevents overdrafts.

```bash
createdb wallet_test_db
pytest tests/ -v
```

## API Overview

All endpoints are prefixed `/api`. Full interactive schema at `/api/docs` (non-production only).

**Auth**
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `POST /api/auth/logout`
- `GET  /api/auth/me`

**Wallet (customer)**
- `POST /api/wallet/` — create wallet
- `GET  /api/wallet/` — list my wallets
- `GET  /api/wallet/{id}` — view a wallet
- `POST /api/wallet/deposit/` (supports `Idempotency-Key` header)
- `POST /api/wallet/withdraw/` (supports `Idempotency-Key` header)
- `POST /api/wallet/transfer/` (supports `Idempotency-Key` header)
- `GET  /api/wallet/transactions/` — paginated, filterable history
- `GET  /api/wallet/transactions/{id}`

**Admin**
- `GET  /api/admin/users`
- `GET  /api/admin/wallets`
- `POST /api/admin/wallets/{id}/freeze/`
- `POST /api/admin/wallets/{id}/unfreeze/`
- `POST /api/admin/wallets/{id}/adjust-balance/`
- `GET  /api/admin/transactions`
- `GET  /api/admin/transactions/{id}/investigate`

### Creating the first admin

There's no public "become admin" endpoint (by design — that would be a huge security hole). Promote a user directly in the database:

```sql
UPDATE users SET role = 'ADMIN' WHERE email = 'you@example.com';
```

## Design Notes

- **Wallet limits** (`app/models/config.py`, `WalletConfiguration`) are stored in the DB per currency, not hardcoded, per the spec — falls back to defaults in `app/core/config.py` if unconfigured.
- **Transaction references** (`TXN-YYYYMMDD-NNNNNN`) are generated from a PostgreSQL sequence (`transaction_reference_seq`), so uniqueness is guaranteed by the database itself even under heavy concurrent load.
- **Transaction state machine** (`PENDING → COMPLETED | FAILED | CANCELLED`, no transitions out of a terminal state) is enforced in `TransactionService.transition_status`.
- The in-memory rate limiter (`app/api/deps.py`) is process-local — fine for this assignment / single instance. For a real multi-instance deployment, swap it for a Redis-backed limiter.
