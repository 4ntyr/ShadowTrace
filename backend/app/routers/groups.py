from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import (
    ActivityEvent,
    ActivityGroup,
    Conflict,
    Favourite,
    Group,
    GroupAlias,
    GroupRelation,
    HybridLink,
    User,
)
from ..security import current_user
from ..serializers import activity, country_ref, group_ref, state_link
from .scope import ScopeCtx, scope_ctx

router = APIRouter(prefix="/api", tags=["groups"])

CONF_RANK = {"confirmed": 0, "high": 1, "medium": 2, "low": 3}


def _activity_counts(db: Session, days: int) -> tuple[dict[int, int], dict[int, datetime]]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.execute(
        select(ActivityGroup.group_id, func.count(), func.max(ActivityEvent.published_at))
        .join(ActivityEvent, ActivityEvent.id == ActivityGroup.activity_id)
        .where(ActivityEvent.published_at >= since)
        .group_by(ActivityGroup.group_id)
    ).all()
    last_rows = db.execute(
        select(ActivityGroup.group_id, func.max(ActivityEvent.published_at))
        .join(ActivityEvent, ActivityEvent.id == ActivityGroup.activity_id)
        .group_by(ActivityGroup.group_id)
    ).all()
    return {r[0]: r[1] for r in rows}, {r[0]: r[1] for r in last_rows}


@router.get("/groups")
def list_groups(
    q: str | None = Query(None, max_length=100),
    country: str | None = Query(None, min_length=2, max_length=2),
    motivation: str | None = None,
    kind: str | None = None,
    sort: str = Query("activity", pattern="^(activity|name|recent)$"),
    ctx: ScopeCtx = Depends(scope_ctx),
    db: Session = Depends(get_db),
):
    stmt = select(Group).options(selectinload(Group.aliases), selectinload(Group.state_links))
    if ctx.restrict is not None:
        stmt = stmt.where(Group.id.in_(ctx.restrict or {-1}))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Group.name).like(like),
                Group.id.in_(select(GroupAlias.group_id).where(func.lower(GroupAlias.alias).like(like))),
                func.lower(Group.attack_id).like(like),
            )
        )
    if country:
        stmt = stmt.where(Group.origin_country_code == country.upper())
    if motivation:
        stmt = stmt.where(Group.motivation == motivation)
    if kind:
        stmt = stmt.where(Group.kind == kind)
    groups = db.scalars(stmt).all()
    act30, last = _activity_counts(db, 30)
    tech_counts = dict(
        db.execute(select(Group.id, func.count()).join(Group.techniques).group_by(Group.id)).all()
    )

    items = []
    for g in groups:
        best = sorted(g.state_links, key=lambda l: CONF_RANK.get(l.confidence, 9))
        items.append(
            {
                **group_ref(g),
                "attack_id": g.attack_id,
                "aliases": [a.alias for a in g.aliases][:8],
                "motivation": g.motivation,
                "summary": g.summary or (g.description[:280] + ("…" if len(g.description) > 280 else "")),
                "curated": "curated" in (g.sources or []),
                "attribution": state_link(best[0]) if best else None,
                "technique_count": tech_counts.get(g.id, 0),
                "activity_30d": act30.get(g.id, 0),
                "last_activity_at": last[g.id].isoformat() if g.id in last else None,
                "is_favourite": g.id in ctx.favourite_ids,
            }
        )
    if sort == "name":
        items.sort(key=lambda x: x["name"].lower())
    elif sort == "recent":
        items.sort(key=lambda x: x["last_activity_at"] or "", reverse=True)
    else:
        items.sort(key=lambda x: (-x["activity_30d"], not x["curated"], x["last_activity_at"] is None, x["name"].lower()))
    return {"total": len(items), "items": items}


@router.get("/groups/{slug}")
def group_detail(slug: str, ctx: ScopeCtx = Depends(scope_ctx), db: Session = Depends(get_db)):
    g = db.scalar(
        select(Group)
        .where(Group.slug == slug)
        .options(
            selectinload(Group.aliases),
            selectinload(Group.state_links),
            selectinload(Group.history),
            selectinload(Group.techniques),
            selectinload(Group.software),
        )
    )
    if g is None:
        raise HTTPException(404, "Group not found")

    relations = []
    rels = db.scalars(
        select(GroupRelation).where(
            or_(GroupRelation.source_group_id == g.id, GroupRelation.target_group_id == g.id)
        )
    ).all()
    for r in rels:
        other = r.target_group if r.source_group_id == g.id else r.source_group
        relations.append(
            {
                "group": group_ref(other),
                "relation": r.relation,
                "direction": "out" if r.source_group_id == g.id else "in",
                "description": r.description,
                "confidence": r.confidence,
                "source_name": r.source_name,
                "source_url": r.source_url,
            }
        )

    by_tactic: dict[str, list] = defaultdict(list)
    for t in sorted(g.techniques, key=lambda t: t.attack_id):
        for tac in t.tactics or ["other"]:
            by_tactic[tac].append({"id": t.attack_id, "name": t.name})

    history = sorted(
        (
            {
                "date": h.date.isoformat(),
                "end_date": h.end_date.isoformat() if h.end_date else None,
                "precision": h.date_precision,
                "title": h.title,
                "description": h.description,
                "kind": h.kind,
                "origin": h.origin,
                "source_name": h.source_name,
                "source_url": h.source_url,
            }
            for h in g.history
        ),
        key=lambda x: x["date"],
    )

    recent = db.scalars(
        select(ActivityEvent)
        .join(ActivityGroup, ActivityGroup.activity_id == ActivityEvent.id)
        .where(ActivityGroup.group_id == g.id)
        .options(selectinload(ActivityEvent.group_links).selectinload(ActivityGroup.group))
        .order_by(ActivityEvent.published_at.desc())
        .limit(25)
    ).all()

    since = datetime.now(timezone.utc) - timedelta(days=365)
    monthly = Counter(
        d.strftime("%Y-%m")
        for d in db.scalars(
            select(ActivityEvent.published_at)
            .join(ActivityGroup, ActivityGroup.activity_id == ActivityEvent.id)
            .where(ActivityGroup.group_id == g.id, ActivityEvent.published_at >= since)
        )
    )
    months = []
    cur = since.replace(day=1)
    while cur <= datetime.now(timezone.utc):
        key = cur.strftime("%Y-%m")
        months.append({"month": key, "count": monthly.get(key, 0)})
        cur = (cur + timedelta(days=32)).replace(day=1)

    hybrid = db.execute(
        select(Conflict.slug, Conflict.name, func.count(HybridLink.id))
        .join(HybridLink, HybridLink.conflict_id == Conflict.id)
        .join(ActivityGroup, ActivityGroup.activity_id == HybridLink.activity_id)
        .where(ActivityGroup.group_id == g.id)
        .group_by(Conflict.slug, Conflict.name)
    ).all()

    return {
        **group_ref(g),
        "attack_id": g.attack_id,
        "mitre_url": g.mitre_url,
        "aliases": [{"alias": a.alias, "source": a.source} for a in g.aliases],
        "summary": g.summary,
        "description": g.description,
        "motivation": g.motivation,
        "first_seen": g.first_seen.isoformat() if g.first_seen else None,
        "sources": g.sources,
        "target_countries": [country_ref(c) for c in g.target_countries or []],
        "target_sectors": g.target_sectors or [],
        "state_links": [state_link(l) for l in sorted(g.state_links, key=lambda l: CONF_RANK.get(l.confidence, 9))],
        "relations": relations,
        "history": history,
        "techniques_by_tactic": by_tactic,
        "technique_count": len(g.techniques),
        "software": [
            {"id": s.attack_id, "name": s.name, "type": s.type} for s in sorted(g.software, key=lambda s: s.name)
        ],
        "activity_monthly": months,
        "recent_activity": [activity(e) for e in recent],
        "hybrid_conflicts": [{"slug": s, "name": n, "links": c} for s, n, c in hybrid],
        "is_favourite": g.id in ctx.favourite_ids,
    }


# ─────────────────────────── favourites ───────────────────────────


@router.get("/favourites")
def list_favourites(user: User = Depends(current_user), db: Session = Depends(get_db)):
    favs = db.scalars(
        select(Favourite).where(Favourite.user_id == user.id).order_by(Favourite.created_at.desc())
    ).all()
    return [{**group_ref(f.group), "added_at": f.created_at.isoformat()} for f in favs]


@router.put("/favourites/{slug}", status_code=204)
def add_favourite(slug: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    g = db.scalar(select(Group).where(Group.slug == slug))
    if g is None:
        raise HTTPException(404, "Group not found")
    if db.get(Favourite, (user.id, g.id)) is None:
        db.add(Favourite(user_id=user.id, group_id=g.id))
        db.commit()


@router.delete("/favourites/{slug}", status_code=204)
def remove_favourite(slug: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    g = db.scalar(select(Group).where(Group.slug == slug))
    if g is None:
        raise HTTPException(404, "Group not found")
    fav = db.get(Favourite, (user.id, g.id))
    if fav:
        db.delete(fav)
        db.commit()


@router.get("/countries")
def countries_with_groups(db: Session = Depends(get_db)):
    rows = db.execute(
        select(Group.origin_country_code, func.count())
        .where(Group.origin_country_code.is_not(None))
        .group_by(Group.origin_country_code)
    ).all()
    return sorted(
        ({**country_ref(code), "groups": n} for code, n in rows), key=lambda x: -x["groups"]
    )
