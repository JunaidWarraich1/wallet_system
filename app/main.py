import logging

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.api.routers import admin, auth, wallet
from app.core.config import settings
from app.core.exceptions import AppError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("wallet_system")

app = FastAPI(
    title=settings.APP_NAME,
    docs_url="/api/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/api/redoc" if settings.ENVIRONMENT != "production" else None,
    openapi_url="/api/openapi.json" if settings.ENVIRONMENT != "production" else None,
)

# ---------------------------------------------------------------------------
# CORS — explicit allow-list from config, never "*" with credentials.
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)


# ---------------------------------------------------------------------------
# Security headers on every response.
# ---------------------------------------------------------------------------
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    if settings.ENVIRONMENT == "production":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


# ---------------------------------------------------------------------------
# Centralized exception handling.
#
# Services raise domain exceptions (AppError subclasses) without knowing
# anything about HTTP. This is the ONLY place that converts them into HTTP
# responses, and it deliberately returns SAFE, GENERIC messages for anything
# unexpected — internal exception details, stack traces, and SQL errors are
# NEVER sent to the client, only logged server-side.
# ---------------------------------------------------------------------------
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.error_code, "message": exc.message}},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    # Pydantic validation errors are safe to return (they describe the
    # client's own input), but we still normalize the shape. Error "ctx"
    # dicts can contain non-JSON-serializable values (Decimal, etc.), so we
    # strip ctx rather than let json.dumps blow up into a 500.
    safe_errors = [
        {k: v for k, v in err.items() if k != "ctx"}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": {"code": "VALIDATION_ERROR", "message": "Invalid request data.", "details": safe_errors}},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred."}},
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(auth.router)
app.include_router(wallet.router)
app.include_router(admin.router)


@app.get("/api/health", tags=["Health"])
def health_check():
    return {"status": "ok"}
