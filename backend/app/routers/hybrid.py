"""Hybrid-warfare tracker: cyber ↔ kinetic correlation per conflict."""

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .. import correlation
from ..db import get_db
from ..models import ActivityEvent, ActivityGroup, Conflict, Group, HybridLink, MilitaryEvent
from ..serializers import activity, country_ref, group_ref, military
from .scope import ScopeCtx, scope_ctx

router = APIRouter(prefix="/api/hybrid", tags=["hybrid"])


def _window(c: Conflict, days: int) -> tuple[date, date]:
    today = datetime.now(timezone.utc).date()
    if c.status == "historical" and c.end_date:
        return c.start_date - timedelta(days=c.window_days + 7), c.end_date + timedelta(days=c.window_days + 7)
    end = min(c.end_date or today, today)
    return max(c.start_date - timedelta(days=c.window_days), end - timedelta(days=days)), end


def _conflict_brief(db: Session, c: Conflict) -> dict:
    kin = db.execute(
        select(func.count(), func.max(MilitaryEvent.event_date)).where(MilitaryEvent.conflict_id == c.id)
    ).one()
    links = db.execute(
        select(HybridLink.method, func.count()).where(HybridLink.conflict_id == c.id).group_by(HybridLink.method)
    ).all()
    sources = [s for (s,) in db.execute(
        select(MilitaryEvent.source).where(MilitaryEvent.conflict_id == c.id).distinct()
    )]
    return {
        "slug": c.slug,
        "name": c.name,
        "status": c.status,
        "description": c.description,
        "start_date": c.start_date.isoformat(),
        "end_date": c.end_date.isoformat() if c.end_date else None,
        "theatre": [country_ref(x) for x in c.theatre_countries],
        "parties": [{"name": p["name"], "countries": [country_ref(x) for x in p["countries"]]} for p in c.parties],
        "window_days": c.window_days,
        "kinetic_count": kin[0],
        "last_kinetic_date": kin[1].isoformat() if kin[1] else None,
        "kinetic_sources": sorted(sources),
        "link_counts": dict(links),
    }


@router.get("/conflicts")
def list_conflicts(db: Session = Depends(get_db)):
    cs = db.scalars(select(Conflict)).all()
    out = [_conflict_brief(db, c) for c in cs]
    out.sort(key=lambda x: (x["status"] != "active", x["start_date"]), reverse=False)
    return out


@router.get("/conflicts/{slug}")
def conflict_detail(
    slug: str,
    days: int = Query(90, ge=14, le=1500),
    ctx: ScopeCtx = Depends(scope_ctx),
    db: Session = Depends(get_db),
):
    c = db.scalar(select(Conflict).where(Conflict.slug == slug))
    if c is None:
        raise HTTPException(404, "Conflict not found")
    start, end = _window(c, days)

    series = correlation.daily_series(db, c, start, end)
    lags = correlation.lag_correlation(series, max_lag=min(7, c.window_days * 2 + 1))
    convergence = correlation.convergence_days(series)

    items = correlation.cyber_items(db, c, start, end)
    if ctx.restrict is not None:
        items = [i for i in items if any(gl.group_id in ctx.restrict for gl in i.event.group_links)]
    cyber_ids = {i.event.id for i in items}
    side_of = {i.event.id: sorted(i.sides) for i in items}

    links = db.scalars(
        select(HybridLink)
        .where(HybridLink.conflict_id == c.id)
        .options(
            selectinload(HybridLink.activity).selectinload(ActivityEvent.group_links).selectinload(ActivityGroup.group),
            selectinload(HybridLink.military_event),
        )
        .order_by(HybridLink.method.desc(), HybridLink.score.desc())
    ).all()
    links = [l for l in links if l.activity_id in cyber_ids or ctx.restrict is None]
    links = [l for l in links if start <= l.military_event.event_date <= end or c.status == "historical"]

    kinetic = db.scalars(
        select(MilitaryEvent)
        .where(MilitaryEvent.conflict_id == c.id, MilitaryEvent.event_date >= start, MilitaryEvent.event_date <= end)
        .order_by(MilitaryEvent.intensity.desc())
        .limit(1500)
    ).all()

    # Participating groups with their side and activity in window
    gsides = correlation._group_sides(db, c)
    counts: dict[int, int] = {}
    for i in items:
        for gl in i.event.group_links:
            counts[gl.group_id] = counts.get(gl.group_id, 0) + 1
    participants = []
    if counts:
        for g in db.scalars(select(Group).where(Group.id.in_(counts))):
            participants.append({
                **group_ref(g),
                "sides": sorted(gsides.get(g.id, [])),
                "events": counts[g.id],
                "is_favourite": g.id in ctx.favourite_ids,
            })
    participants.sort(key=lambda p: -p["events"])

    return {
        **_conflict_brief(db, c),
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "series": series,
        "lag_correlation": lags,
        "convergence_days": convergence,
        "participants": participants,
        "cyber_events": [
            {**activity(i.event), "date": i.day.isoformat(), "date_basis": i.basis, "sides": side_of[i.event.id]}
            for i in sorted(items, key=lambda i: i.day, reverse=True)[:300]
        ],
        "kinetic_events": [military(k) for k in kinetic],
        "links": [
            {
                "id": l.id,
                "method": l.method,
                "score": round(l.score, 3),
                "lag_days": l.lag_days,
                "date_basis": l.date_basis,
                "rationale": l.rationale,
                "cyber": activity(l.activity),
                "kinetic": military(l.military_event),
            }
            for l in links[:200]
        ],
    }
