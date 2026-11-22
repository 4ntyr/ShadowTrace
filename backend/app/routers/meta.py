from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import ActivityEvent, FeedStatus, Group, MilitaryEvent

router = APIRouter(prefix="/api", tags=["meta"])

HINTS = {
    "otx": "Free API key from otx.alienvault.com → ST_OTX_API_KEY",
    "acled": "Free account at acleddata.com → ST_ACLED_USERNAME / ST_ACLED_PASSWORD",
    "gdelt": "Keyless; machine-coded from news, so expect geocoding noise",
    "mitre": "Refreshed weekly from github.com/mitre/cti",
}


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("select 1"))
    return {"status": "ok"}


@router.get("/sources")
def sources(db: Session = Depends(get_db)):
    s = get_settings()
    rows = db.scalars(select(FeedStatus).order_by(FeedStatus.kind, FeedStatus.name)).all()
    out = []
    for r in rows:
        out.append(
            {
                "key": r.key,
                "name": r.name,
                "kind": r.kind,
                "configured": r.configured,
                "healthy": r.configured and r.last_error is None and r.last_success_at is not None,
                "last_run_at": r.last_run_at.isoformat() if r.last_run_at else None,
                "last_success_at": r.last_success_at.isoformat() if r.last_success_at else None,
                "last_error": r.last_error,
                "items_last_run": r.items_last_run,
                "hint": HINTS.get(r.kind if r.kind != "rss" else "", None),
            }
        )
    counts = {
        "groups": db.scalar(select(func.count()).select_from(Group)),
        "activity_events": db.scalar(select(func.count()).select_from(ActivityEvent)),
        "military_events": db.scalar(select(func.count()).select_from(MilitaryEvent)),
    }
    return {
        "sources": out,
        "counts": counts,
        "keys": {"otx": bool(s.otx_api_key), "acled": bool(s.acled_username and s.acled_password)},
    }
