"""
SQLAlchemy ORM models.

Design notes (see docs/architecture.md for full rationale):
- `click_count` is a denormalized counter on `Url` for O(1) reads of total
  clicks without scanning `ClickEvent`. It is updated via an atomic SQL
  UPDATE (see crud.record_click) to avoid the classic read-modify-write
  lost-update race condition under concurrent redirects.
- `ClickEvent` stores per-click analytics detail. We hash the client IP
  (SHA-256, not reversible) instead of storing raw IPs, to keep basic abuse/
  analytics signal without retaining PII we don't need.
"""
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    # Stored/compared as naive UTC throughout the app. SQLite has no native
    # timezone-aware datetime type, so mixing naive/aware datetimes here
    # would raise "can't compare offset-naive and offset-aware datetimes".
    # Postgres deployments still get correct UTC semantics since every
    # value written and read by this app is consistently naive-UTC.
    return datetime.now(UTC).replace(tzinfo=None)


class Url(Base):
    __tablename__ = "urls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    original_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    is_custom_alias: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    click_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=_utcnow, nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)

    clicks: Mapped[list["ClickEvent"]] = relationship(
        back_populates="url", cascade="all, delete-orphan"
    )

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        now = now or _utcnow()
        return now >= self.expires_at


class ClickEvent(Base):
    __tablename__ = "click_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url_id: Mapped[int] = mapped_column(
        ForeignKey("urls.id", ondelete="CASCADE"), index=True, nullable=False
    )
    clicked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=_utcnow, nullable=False, index=True
    )
    referrer: Mapped[str | None] = mapped_column(String(512), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    url: Mapped["Url"] = relationship(back_populates="clicks")
