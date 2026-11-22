"""Activity feed and dashboard statistics."""

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..countries import country_name
from ..db import get_db
from ..models import ActivityEvent, ActivityGroup, Group
from ..serializers import activity, country_ref
from .scope import ScopeCtx, scope_ctx

router = APIRouter(prefix="/api/activity", tags=["activity"])


def _base(ctx: ScopeCtx, group: str | None, db: Session):
    stmt = select(ActivityEvent)
    restrict = ctx.restrict
    if group:
        gid = db.scalar(select(Group.id).where(Group.slug == group))
        restrict = {gid or -1} if restrict is None else (restrict & {gid or -1})
    if restrict is not None:
        stmt = stmt.where(
            ActivityEvent.id.in_(
                select(ActivityGroup.activity_id).where(ActivityGroup.group_id.in_(restrict or {-1}))
            )
        )
    return stmt


@router.get("")
def list_activity(
    group: str | None = None,
    source_type: str | None = Query(None, pattern="^(rss|otx|curated)$"),
    country: str | None = Query(None, min_length=2, max_length=2),
    effect: str | None = None,
    q: str | None = Query(None, max_length=100),
    days: int = Query(30, ge=1, le=3650),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: ScopeCtx = Depends(scope_ctx),
    db: Session = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = _base(ctx, group, db).where(ActivityEvent.published_at >= since)
    if source_type:
        stmt = stmt.where(ActivityEvent.source_type == source_type)
    if effect:
        stmt = stmt.where(ActivityEvent.effect == effect)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(ActivityEvent.title).like(like), func.lower(ActivityEvent.summary).like(like)))
    rows = db.scalars(
        stmt.options(selectinload(ActivityEvent.group_links).selectinload(ActivityGroup.group))
        .order_by(ActivityEvent.published_at.desc())
    ).all()
    if country:  # JSON column: filter in Python to stay portable across DBs
        rows = [r for r in rows if country.upper() in (r.countries or [])]
    page = rows[offset : offset + limit]
    return {"total": len(rows), "items": [activity(r) for r in page]}


@router.get("/stats")
def stats(
    days: int = Query(90, ge=7, le=730),
    ctx: ScopeCtx = Depends(scope_ctx),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    rows = db.scalars(
        _base(ctx, None, db)
        .where(ActivityEvent.published_at >= since)
        .options(selectinload(ActivityEvent.group_links).selectinload(ActivityGroup.group))
    ).all()

    restrict = ctx.restrict
    daily = Counter()
    by_country = Counter()
    by_group = Counter()
    by_effect = Counter()
    by_source = Counter()
    weekly_group: dict[int, Counter] = defaultdict(Counter)
    group_obj: dict[int, Group] = {}
    active_7d = set()
    iocs_7d = 0
    events_24h = events_7d = 0
    for ev in rows:
        d = ev.published_at.date()
        daily[d] += 1
        for c in ev.countries or []:
            by_country[c] += 1
        by_effect[ev.effect or "unknown"] += 1
        by_source[ev.source_type] += 1
        week = (d - timedelta(days=d.weekday())).isoformat()
        for gl in ev.group_links:
            if restrict is not None and gl.group_id not in restrict:
                continue
            by_group[gl.group_id] += 1
            weekly_group[gl.group_id][week] += 1
            group_obj[gl.group_id] = gl.group
            if ev.published_at >= now - timedelta(days=7):
                active_7d.add(gl.group_id)
        if ev.published_at >= now - timedelta(days=7):
            events_7d += 1
            iocs_7d += ev.ioc_count
        if ev.published_at >= now - timedelta(hours=24):
            events_24h += 1

    days_list = [(since + timedelta(days=i)).date() for i in range(days + 1)]
    weeks = sorted({(d - timedelta(days=d.weekday())).isoformat() for d in days_list})
    top = [gid for gid, _ in by_group.most_common(12)]
    return {
        "days": days,
        "totals": {
            "events_24h": events_24h,
            "events_7d": events_7d,
            "events_period": len(rows),
            "groups_active_7d": len(active_7d),
            "iocs_7d": iocs_7d,
        },
        "daily": [{"date": d.isoformat(), "count": daily.get(d, 0)} for d in days_list],
        "by_country": [{**country_ref(c), "count": n} for c, n in by_country.most_common()],
        "by_group": [
            {"slug": group_obj[g].slug, "name": group_obj[g].name, "country": group_obj[g].origin_country_code,
             "count": n}
            for g, n in by_group.most_common(15)
        ],
        "by_effect": [{"effect": k, "count": v} for k, v in by_effect.most_common()],
        "by_source": [{"source": k, "count": v} for k, v in by_source.most_common()],
        "heatmap": {
            "weeks": weeks,
            "groups": [
                {"slug": group_obj[g].slug, "name": group_obj[g].name,
                 "country": country_name(group_obj[g].origin_country_code) if group_obj[g].origin_country_code else None,
                 "counts": [weekly_group[g].get(w, 0) for w in weeks]}
                for g in top
            ],
        },
    }
