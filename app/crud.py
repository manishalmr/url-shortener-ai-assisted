"""
Database access layer.

Notable design decision - atomic click counting:
    An earlier version of this function (kept here in a comment for the
    brownfield case study in docs/scenarios.md) incremented the counter as:

        db_url.click_count += 1
        db.commit()

    Under concurrent redirects this is a classic read-modify-write race:
    two requests can both read click_count=N, both compute N+1, and the
    second commit silently overwrites the first, losing a click. Fixed
    below by pushing the increment into a single atomic SQL UPDATE
    (`click_count = click_count + 1`), which the database executes
    atomically regardless of concurrent callers.

Notable design decision - concurrent duplicate-alias creation:
    create_url() below checks `code_exists()` before inserting - a classic
    check-then-act pattern. Two concurrent requests for the same custom
    alias can both pass that check before either commits (neither sees the
    other's uncommitted row), so both attempt to INSERT the same `code`.
    The database's UNIQUE constraint on `Url.code` (models.py) correctly
    rejects the second insert - but without the try/except below, that
    raised a raw `IntegrityError`, which had no handler and surfaced to
    callers as an unhandled 500 instead of the clean 409 a sequential
    duplicate request gets. Confirmed live with a two-thread race probe
    before this fix (see docs/scenarios.md for the case study). Fixed by
    catching the IntegrityError and translating it into the same
    AliasUnavailableError a sequential duplicate produces.
"""
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.exceptions import AliasUnavailableError, CodeGenerationExhaustedError
from app.models import ClickEvent, Url, _utcnow
from app.shortener import generate_code, is_reserved


def get_by_original_url(db: Session, original_url: str) -> Url | None:
    stmt = select(Url).where(Url.original_url == original_url, Url.is_active.is_(True))
    return db.execute(stmt).scalar_one_or_none()


def get_by_code(db: Session, code: str) -> Url | None:
    stmt = select(Url).where(Url.code == code)
    return db.execute(stmt).scalar_one_or_none()


def code_exists(db: Session, code: str) -> bool:
    return get_by_code(db, code) is not None


def create_url(
    db: Session,
    *,
    original_url: str,
    custom_alias: str | None,
    expires_in_days: int | None,
    code_length: int,
    max_attempts: int,
) -> tuple[Url, bool]:
    """Returns (url_row, was_newly_created)."""
    if custom_alias:
        if is_reserved(custom_alias) or code_exists(db, custom_alias):
            raise ValueError("alias_unavailable")
        code = custom_alias
        is_custom = True
    else:
        code = None
        for _ in range(max_attempts):
            candidate = generate_code(code_length)
            if not is_reserved(candidate) and not code_exists(db, candidate):
                code = candidate
                break
        if code is None:
            raise CodeGenerationExhaustedError(
                "Could not generate a unique short code; try again."
            )
        is_custom = False

    expires_at = None
    if expires_in_days:
        expires_at = _utcnow() + timedelta(days=expires_in_days)

    row = Url(
        code=code,
        original_url=original_url,
        is_custom_alias=is_custom,
        expires_at=expires_at,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        # See module docstring: the check-then-act race window between
        # code_exists() and this commit. The DB's UNIQUE constraint is the
        # real safety net (no duplicate rows can ever exist); this just
        # gives the loser of the race a clean, expected error instead of a
        # raw 500.
        db.rollback()
        raise AliasUnavailableError(
            f"Alias '{code}' was just taken by a concurrent request. Please try again."
        ) from None
    db.refresh(row)
    return row, True


def soft_delete(db: Session, url_row: Url) -> None:
    url_row.is_active = False
    url_row.deleted_at = _utcnow()
    db.commit()


def list_urls(db: Session, *, limit: int, offset: int, active_only: bool) -> tuple[list[Url], int]:
    stmt = select(Url)
    if active_only:
        stmt = stmt.where(Url.is_active.is_(True))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    stmt = stmt.order_by(Url.created_at.desc()).limit(limit).offset(offset)
    items = list(db.execute(stmt).scalars().all())
    return items, total


def record_click(
    db: Session,
    url_row: Url,
    *,
    referrer: str | None,
    user_agent: str | None,
    ip_hash: str | None,
) -> None:
    # Atomic counter increment - see module docstring for the race condition
    # this replaced.
    db.execute(
        update(Url).where(Url.id == url_row.id).values(click_count=Url.click_count + 1)
    )
    db.add(
        ClickEvent(
            url_id=url_row.id,
            referrer=referrer,
            user_agent=user_agent,
            ip_hash=ip_hash,
        )
    )
    db.commit()


def get_analytics_raw(db: Session, url_row: Url, *, days: int = 14):
    since = _utcnow() - timedelta(days=days)
    events_stmt = (
        select(ClickEvent)
        .where(ClickEvent.url_id == url_row.id, ClickEvent.clicked_at >= since)
        .order_by(ClickEvent.clicked_at.desc())
    )
    events = list(db.execute(events_stmt).scalars().all())

    last_24h_cutoff = _utcnow() - timedelta(hours=24)
    clicks_last_24h = sum(1 for e in events if e.clicked_at >= last_24h_cutoff)

    last_clicked_at = events[0].clicked_at if events else None
    return events, clicks_last_24h, last_clicked_at
