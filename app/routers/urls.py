from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app import crud
from app.cache import TTLLRUCache
from app.config import settings
from app.database import get_db
from app.exceptions import (
    AliasUnavailableError,
    InvalidURLError,
    RateLimitExceededError,
    URLNotFoundError,
)
from app.qrcode_service import generate_qr_png
from app.rate_limiter import FixedWindowRateLimiter
from app.schemas import PaginatedURLsResponse, URLCreateRequest, URLDetailResponse, URLResponse
from app.security import validate_original_url

router = APIRouter(prefix="/api/v1/urls", tags=["urls"])

redirect_cache = TTLLRUCache(
    max_size=settings.cache_max_size, ttl_seconds=settings.cache_ttl_seconds
)
create_rate_limiter = FixedWindowRateLimiter(settings.rate_limit_create_per_minute)


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _to_response(url_row) -> URLResponse:
    return URLResponse(
        code=url_row.code,
        short_url=f"{settings.base_url.rstrip('/')}/{url_row.code}",
        original_url=url_row.original_url,
        created_at=url_row.created_at,
        expires_at=url_row.expires_at,
        is_custom_alias=url_row.is_custom_alias,
    )


def _to_detail_response(url_row) -> URLDetailResponse:
    base = _to_response(url_row)
    return URLDetailResponse(
        **base.model_dump(), is_active=url_row.is_active, click_count=url_row.click_count
    )


@router.post("", response_model=URLResponse, status_code=201)
def create_short_url(payload: URLCreateRequest, request: Request, db: Session = Depends(get_db)):
    if not create_rate_limiter.allow(_client_key(request)):
        raise RateLimitExceededError("Too many URL creation requests. Please slow down.")

    try:
        validated_url = validate_original_url(payload.original_url)
    except ValueError as exc:
        raise InvalidURLError(str(exc)) from exc

    if not payload.custom_alias and settings.dedup_existing_urls:
        existing = crud.get_by_original_url(db, validated_url)
        if existing is not None and not existing.is_expired():
            return _to_response(existing)

    try:
        url_row, _created = crud.create_url(
            db,
            original_url=validated_url,
            custom_alias=payload.custom_alias,
            expires_in_days=payload.expires_in_days or settings.default_expiry_days,
            code_length=settings.code_length,
            max_attempts=settings.max_code_generation_attempts,
        )
    except ValueError as exc:
        if str(exc) == "alias_unavailable":
            raise AliasUnavailableError(
                f"Alias '{payload.custom_alias}' is already taken or reserved."
            ) from exc
        raise

    return _to_response(url_row)


@router.get("", response_model=PaginatedURLsResponse)
def list_short_urls(
    limit: int = 20, offset: int = 0, active_only: bool = True, db: Session = Depends(get_db)
):
    limit = max(1, min(limit, 100))
    items, total = crud.list_urls(db, limit=limit, offset=offset, active_only=active_only)
    return PaginatedURLsResponse(
        items=[_to_detail_response(i) for i in items], total=total, limit=limit, offset=offset
    )


@router.get("/{code}", response_model=URLDetailResponse)
def get_short_url(code: str, db: Session = Depends(get_db)):
    url_row = crud.get_by_code(db, code)
    if url_row is None:
        raise URLNotFoundError(f"No short URL found for code '{code}'")
    return _to_detail_response(url_row)


@router.delete("/{code}", status_code=204)
def delete_short_url(code: str, db: Session = Depends(get_db)):
    url_row = crud.get_by_code(db, code)
    if url_row is None:
        raise URLNotFoundError(f"No short URL found for code '{code}'")
    crud.soft_delete(db, url_row)
    redirect_cache.invalidate(code)
    return Response(status_code=204)


@router.get("/{code}/qrcode")
def get_short_url_qrcode(code: str, db: Session = Depends(get_db)):
    """See app/qrcode_service.py for the ambiguity/assumption write-up."""
    url_row = crud.get_by_code(db, code)
    if url_row is None:
        raise URLNotFoundError(f"No short URL found for code '{code}'")
    short_url = f"{settings.base_url.rstrip('/')}/{url_row.code}"
    png_bytes = generate_qr_png(short_url)
    return Response(content=png_bytes, media_type="image/png")
