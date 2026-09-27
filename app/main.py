"""
FastAPI application entrypoint.

Route ordering matters here: the catch-all redirect route (`GET /{code}`)
is registered LAST so that `/api/*`, `/health`, and `/docs` are matched
first. This is a deliberate architectural decision - see
docs/architecture.md#control-flow.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.database import init_db
from app.exceptions import URLShortenerError
from app.middleware import RequestLoggingMiddleware, SecurityHeadersMiddleware, configure_logging
from app.routers import analytics, health, redirect, urls

configure_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="URL Shortener",
    description="AI-assisted URL shortener service with analytics and reliability controls.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)


@app.exception_handler(URLShortenerError)
async def domain_error_handler(request: Request, exc: URLShortenerError):
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.error_code, "detail": exc.detail, "request_id": request_id},
    )


# Order matters: specific routers before the catch-all redirect router.
app.include_router(health.router)
app.include_router(urls.router)
app.include_router(analytics.router)
app.include_router(redirect.router)
