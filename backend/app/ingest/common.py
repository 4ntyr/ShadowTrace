"""Shared plumbing for connectors: run bookkeeping and activity upserts."""

import logging
import traceback
from collections.abc import Callable
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ActivityEvent, ActivityGroup, Conflict, FeedStatus, Group
from .matcher import GroupMatcher
from .textintel import detect_countries, detect_effect, detect_sectors

log = logging.getLogger(__name__)


class NotConfigured(Exception):
    """Raised by a connector when its credentials are missing; recorded, not treated as failure."""


def http_client(timeout: float = 30) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": get_settings().http_user_agent},
    )


def status_row(db: Session, key: str, name: str, kind: str) -> FeedStatus:
    row = db.get(FeedStatus, key)
    if row is None:
        row = FeedStatus(key=key, name=name, kind=kind, state={})
        db.add(row)
        db.flush()
    return row


def run_tracked(db: Session, key: str, name: str, kind: str, fn: Callable[[FeedStatus], int]) -> int:
    """Run a connector, recording timing, item counts and errors in feed_status."""
    row = status_row(db, key, name, kind)
    row.last_run_at = datetime.now(timezone.utc)
    db.commit()
    try:
        n = fn(row)
    except NotConfigured as e:
        db.rollback()
        row = status_row(db, key, name, kind)
        row.configured = False
        row.last_error = str(e)
        row.items_last_run = 0
        db.commit()
        return 0
    except Exception as e:  # noqa: BLE001 - one bad source must not stop the others
        db.rollback()
        log.warning("connector %s failed: %s", key, e)
        row = status_row(db, key, name, kind)
        row.configured = True
        row.last_error = f"{type(e).__name__}: {e}"[:2000]
        row.items_last_run = 0
        log.debug(traceback.format_exc())
        db.commit()
        return 0
    row.configured = True
    row.last_error = None
    row.last_success_at = datetime.now(timezone.utc)
    row.items_last_run = n
    db.commit()
    return n


def store_activity(
    db: Session,
    matcher: GroupMatcher,
    *,
    source_key: str,
    source_type: str,
    source_name: str,
    external_id: str,
    title: str,
    summary: str,
    url: str | None,
    published_at: datetime,
    extra_group_ids: list[tuple[int, str, str]] | None = None,
    countries: list[str] | None = None,
    sectors: list[str] | None = None,
    tags: list[str] | None = None,
    ioc_count: int = 0,
    require_group: bool = True,
) -> ActivityEvent | None:
    """Create an ActivityEvent if it mentions a tracked group. Returns None if skipped/duplicate."""
    external_id = external_id[:500]
    exists = db.scalar(
        select(ActivityEvent.id).where(
            ActivityEvent.source_key == source_key, ActivityEvent.external_id == external_id
        )
    )
    if exists:
        return None

    text = f"{title}\n{summary}"
    links: dict[int, tuple[str, str]] = {}
    for gid, method, matched in extra_group_ids or []:
        links[gid] = (method, matched)
    for m in matcher.match(text):
        links.setdefault(m.group_id, ("alias", m.text))
    if require_group and not links:
        return None

    # Countries mentioned minus the attackers' own origin countries ≈ targeted countries.
    origin = set()
    if links:
        origin = {
            c for c in db.scalars(select(Group.origin_country_code).where(Group.id.in_(links)))
            if c
        }
    detected = [c for c in detect_countries(text) if c not in origin]
    all_countries = list(dict.fromkeys([*(countries or []), *detected]))

    ev = ActivityEvent(
        source_key=source_key,
        source_type=source_type,
        source_name=source_name,
        external_id=external_id,
        title=title[:500],
        summary=summary,
        url=url,
        published_at=published_at,
        countries=all_countries,
        sectors=list(dict.fromkeys([*(sectors or []), *detect_sectors(text)])),
        tags=tags or [],
        effect=detect_effect(text),
        ioc_count=ioc_count,
    )
    for gid, (method, matched) in links.items():
        ev.group_links.append(ActivityGroup(group_id=gid, match_method=method, matched_text=matched[:200]))
    db.add(ev)
    return ev


def active_conflicts(db: Session, today=None) -> list[Conflict]:
    today = today or datetime.now(timezone.utc).date()
    return [
        c for c in db.scalars(select(Conflict))
        if c.status == "active" and (c.end_date is None or c.end_date >= today)
    ]


def conflict_for(conflicts: list[Conflict], country: str | None, day) -> Conflict | None:
    if not country:
        return None
    for c in conflicts:
        if country in c.theatre_countries and c.start_date <= day and (c.end_date is None or day <= c.end_date):
            return c
    return None
