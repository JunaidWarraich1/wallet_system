"""
Central application configuration.

SECURITY NOTE:
All secrets (DB credentials, JWT signing key, etc.) are loaded from environment
variables / a .env file. NOTHING sensitive is hardcoded in source code, which
means it can never leak through version control by accident.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- App ---
    APP_NAME: str = "Digital Wallet & Money Transfer System"
    ENVIRONMENT: str = "development"  # development | staging | production
    DEBUG: bool = False

    # --- Database ---
    DATABASE_URL: str  # e.g. postgresql+psycopg2://user:pass@localhost:5432/wallet_db

    # --- JWT / Auth ---
    JWT_SECRET_KEY: str          # MUST be set via env, long random string
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- Password policy ---
    PASSWORD_MIN_LENGTH: int = 10
    BCRYPT_ROUNDS: int = 12

    # --- Account lockout (brute force protection) ---
    MAX_FAILED_LOGIN_ATTEMPTS: int = 5
    ACCOUNT_LOCKOUT_MINUTES: int = 15

    # --- Rate limiting ---
    RATE_LIMIT_PER_MINUTE: int = 60
    TRANSFER_RATE_LIMIT_PER_MINUTE: int = 10

    # --- Wallet business limits (defaults; can be overridden per-config record in DB) ---
    DEFAULT_MAX_SINGLE_DEPOSIT: int = 1_000_000
    DEFAULT_MAX_SINGLE_WITHDRAWAL: int = 50_000
    DEFAULT_MAX_DAILY_WITHDRAWAL: int = 100_000
    DEFAULT_MAX_SINGLE_TRANSFER: int = 100_000
    DEFAULT_MAX_DAILY_TRANSFER: int = 500_000

    # --- CORS ---
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
