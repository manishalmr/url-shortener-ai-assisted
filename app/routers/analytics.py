from collections import Counter, defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.exceptions import URLNotFoundError
from app.schemas import AnalyticsResponse, DailyClickCount, ReferrerCount

router = APIRouter(prefix="/api/v1/urls", tags=["analytics"])


@router.get("/{code}/analytics", response_model=AnalyticsResponse)
def get_analytics(code: str, db: Session = Depends(get_db)):
    url_row = crud.get_by_code(db, code)
    if url_row is None:
        raise URLNotFoundError(f"No short URL found for code '{code}'")

    events, clicks_last_24h, last_clicked_at = crud.get_analytics_raw(db, url_row)

    by_day: dict[str, int] = defaultdict(int)
    referrers: Counter = Counter()
    for event in events:
        by_day[event.clicked_at.date().isoformat()] += 1
        referrers[event.referrer or "direct/unknown"] += 1

    clicks_by_day = [
        DailyClickCount(date=d, clicks=c) for d, c in sorted(by_day.items())
    ]
    top_referrers = [
        ReferrerCount(referrer=r, clicks=c) for r, c in referrers.most_common(5)
    ]

    return AnalyticsResponse(
        code=code,
        total_clicks=url_row.click_count,
        clicks_last_24h=clicks_last_24h,
        last_clicked_at=last_clicked_at,
        clicks_by_day=clicks_by_day,
        top_referrers=top_referrers,
    )
