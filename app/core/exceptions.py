"""
Domain-level exceptions.

Business rule violations raise these from the Service layer. The API layer
(app/api/routers/*) catches them centrally via exception handlers in main.py
and converts them into safe, consistent HTTP responses — so services never
need to know about HTTP status codes, and internal details never leak to
clients (see main.py exception handlers for how messages are sanitized).
"""


class AppError(Exception):
    """Base class for all expected application errors."""
    status_code = 400
    error_code = "APP_ERROR"

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ValidationError(AppError):
    status_code = 422
    error_code = "VALIDATION_ERROR"


class NotFoundError(AppError):
    status_code = 404
    error_code = "NOT_FOUND"


class AuthenticationError(AppError):
    status_code = 401
    error_code = "AUTHENTICATION_ERROR"


class AuthorizationError(AppError):
    status_code = 403
    error_code = "AUTHORIZATION_ERROR"


class ConflictError(AppError):
    status_code = 409
    error_code = "CONFLICT"


class BusinessRuleError(AppError):
    """Raised for any business-rule violation, e.g. insufficient balance,
    frozen wallet, limit exceeded, self-transfer, etc."""
    status_code = 422
    error_code = "BUSINESS_RULE_VIOLATION"


class RateLimitError(AppError):
    status_code = 429
    error_code = "RATE_LIMIT_EXCEEDED"


class AccountLockedError(AppError):
    status_code = 423
    error_code = "ACCOUNT_LOCKED"
