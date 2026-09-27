import hashlib

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app import crud
from app.config import settings
from app.database import get_db
from app.exceptions import RateLimitExceededError, URLGoneError, URLNotFoundError
from app.rate_limiter import FixedWindowRateLimiter
from app.routers.urls import redirect_cache

router = APIRouter(tags=["redirect"])

redirect_rate_limiter = FixedWindowRateLimiter(settings.rate_limit_redirect_per_minute)


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _hash_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()


@router.get("/{code}")
def redirect_to_original(code: str, request: Request, db: Session = Depends(get_db)):
    if not redirect_rate_limiter.allow(_client_key(request)):
        raise RateLimitExceededError("Too many requests. Please slow down.")

    cached = redirect_cache.get(code)
    url_row = cached if cached is not None else crud.get_by_code(db, code)

    if url_row is None:
        raise URLNotFoundError(f"No short URL found for code '{code}'")
    if not url_row.is_active:
        raise URLGoneError(f"Short URL '{code}' has been deleted")
    if url_row.is_expired():
        raise URLGoneError(f"Short URL '{code}' has expired")

    if cached is None:
        redirect_cache.set(code, url_row)

    crud.record_click(
        db,
        url_row,
        referrer=request.headers.get("referer"),
        user_agent=request.headers.get("user-agent"),
        ip_hash=_hash_ip(request.client.host if request.client else None),
    )

    return RedirectResponse(url=url_row.original_url, status_code=307)
