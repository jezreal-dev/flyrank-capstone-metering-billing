"""FastAPI main application entrypoint for LLM Usage Metering & Billing Engine."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import init_db
from app.api.router import api_router
from app.services.quota_service import QuotaExceededException

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite tables, foreign keys, and indexes
    init_db()
    yield

app = FastAPI(
    title="LLM Usage Metering & Billing Engine",
    description="Production-grade SaaS usage metering, quota enforcement, money math, and Stripe synchronization",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================================
# Shared Requirement 2: Boundary Validation & Clean HTTP Errors (Never 500)
# ==============================================================================
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation Error",
            "message": "Input payload failed schema validation at boundary",
            "details": exc.errors()
        }
    )

@app.exception_handler(QuotaExceededException)
async def quota_exception_handler(request: Request, exc: QuotaExceededException):
    headers = {"Retry-After": str(exc.retry_after)} if exc.status_code == 429 else {}
    return JSONResponse(
        status_code=exc.status_code,
        headers=headers,
        content={
            "error": "Quota Exceeded" if exc.status_code == 429 else "Payment Required",
            "message": exc.message,
            "status_code": exc.status_code
        }
    )

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "Bad Request",
            "message": str(exc)
        }
    )

app.include_router(api_router)

@app.get("/health", tags=["health"])
def health_check():
    return {
        "status": "healthy",
        "service": "metering-billing-engine",
        "version": "1.0.0",
        "database": "sqlite_wal_enabled"
    }

@app.get("/", tags=["root"])
def root():
    return {
        "title": "LLM Usage Metering & Billing Engine",
        "docs": "/docs",
        "health": "/health",
        "plans": "/api/plans"
    }
