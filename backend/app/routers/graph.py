"""Relationship graph: groups ↔ states (attribution, targeting) and groups ↔ groups."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..countries import country_name
from ..db import get_db
from ..models import ActivityEvent, ActivityGroup, Group, GroupRelation
from .scope import Scope, ScopeCtx, scope_ctx

router = APIRouter(prefix="/api", tags=["graph"])
CONF_RANK = {"confirmed": 0, "high": 1, "medium": 2, "low": 3}


@router.get("/graph")
def graph(
    include_targets: bool = False,
    include_unattributed: bool = False,
    min_confidence: str = Query("low", pattern="^(confirmed|high|medium|low)$"),
    ctx: ScopeCtx = Depends(scope_ctx),
    db: Session = Depends(get_db),
):
    max_rank = CONF_RANK[min_confidence]
    groups = {g.id: g for g in db.scalars(select(Group).options(selectinload(Group.state_links)))}
    relations = db.scalars(select(GroupRelation)).all()

    since = datetime.now(timezone.utc) - timedelta(days=30)
    act = dict(
        db.execute(
            select(ActivityGroup.group_id, func.count())
            .join(ActivityEvent, ActivityEvent.id == ActivityGroup.activity_id)
            .where(ActivityEvent.published_at >= since)
            .group_by(ActivityGroup.group_id)
        ).all()
    )

    if ctx.scope == Scope.favourites:
        core = set(ctx.favourite_ids)
        context = set()
        for r in relations:
            if r.source_group_id in core:
                context.add(r.target_group_id)
            if r.target_group_id in core:
                context.add(r.source_group_id)
        selected = core | context
    else:
        core = set()
        related = {r.source_group_id for r in relations} | {r.target_group_id for r in relations}
        selected = {
            gid for gid, g in groups.items()
            if include_unattributed or gid in related
            or any(CONF_RANK.get(l.confidence, 9) <= max_rank for l in g.state_links)
        }

    nodes, edges = [], []
    states: dict[str, int] = {}
    for gid in selected:
        g = groups[gid]
        nodes.append(
            {
                "id": f"g:{g.slug}",
                "type": "group",
                "slug": g.slug,
                "label": g.name,
                "kind": g.kind,
                "motivation": g.motivation,
                "country": g.origin_country_code,
                "activity_30d": act.get(gid, 0),
                "favourite": gid in ctx.favourite_ids,
                "context": ctx.scope == Scope.favourites and gid not in core,
            }
        )
        for l in g.state_links:
            if CONF_RANK.get(l.confidence, 9) > max_rank:
                continue
            states[l.country_code] = states.get(l.country_code, 0) + 1
            edges.append(
                {
                    "source": f"g:{g.slug}",
                    "target": f"s:{l.country_code}",
                    "type": "attribution",
                    "relation": l.relation,
                    "confidence": l.confidence,
                    "origin": l.origin,
                    "agency": l.agency,
                }
            )
        if include_targets:
            for cc in g.target_countries or []:
                states.setdefault(cc, 0)
                edges.append({"source": f"g:{g.slug}", "target": f"s:{cc}", "type": "targets"})

    for r in relations:
        if r.source_group_id in selected and r.target_group_id in selected:
            edges.append(
                {
                    "source": f"g:{groups[r.source_group_id].slug}",
                    "target": f"g:{groups[r.target_group_id].slug}",
                    "type": "relation",
                    "relation": r.relation,
                    "confidence": r.confidence,
                    "description": r.description,
                }
            )

    for code, n in states.items():
        nodes.append({"id": f"s:{code}", "type": "state", "code": code, "label": country_name(code), "groups": n})
    return {"nodes": nodes, "edges": edges}
