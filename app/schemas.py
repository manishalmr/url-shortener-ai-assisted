"""Pydantic request/response schemas (API contract)."""
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class URLCreateRequest(BaseModel):
    original_url: str = Field(..., description="The long URL to shorten")
    custom_alias: str | None = Field(
        None, min_length=3, max_length=32, description="Optional custom short code"
    )
    expires_in_days: int | None = Field(
        None, ge=1, le=3650, description="Optional expiry window in days from creation"
    )

    @field_validator("original_url")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("original_url must not be blank")
        return v.strip()

    @field_validator("custom_alias")
    @classmethod
    def alias_charset(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("custom_alias may only contain letters, numbers, '-' and '_'")
        return v


class URLResponse(BaseModel):
    code: str
    short_url: str
    original_url: str
    created_at: datetime
    expires_at: datetime | None
    is_custom_alias: bool


class URLDetailResponse(URLResponse):
    is_active: bool
    click_count: int


class PaginatedURLsResponse(BaseModel):
    items: list[URLDetailResponse]
    total: int
    limit: int
    offset: int


class DailyClickCount(BaseModel):
    date: str
    clicks: int


class ReferrerCount(BaseModel):
    referrer: str
    clicks: int


class AnalyticsResponse(BaseModel):
    code: str
    total_clicks: int
    clicks_last_24h: int
    last_clicked_at: datetime | None
    clicks_by_day: list[DailyClickCount]
    top_referrers: list[ReferrerCount]


class ErrorResponse(BaseModel):
    error: str
    detail: str
    request_id: str | None = None
