"""AlienVault OTX connector (pulses from the key owner's subscriptions)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..config import get_settings
from ..countries import iso2_from_name
from ..util import strip_html, to_utc
from .common import FeedStatus, NotConfigured, http_client, run_tracked, store_activity
from .matcher import GroupMatcher

MAX_PAGES = 10


def _ts(s: str | None) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    return to_utc(datetime.fromisoformat(s.replace("Z", "+00:00")))


def ingest_pulses(db: Session, matcher: GroupMatcher, pulses: list[dict]) -> int:
    n = 0
    for p in pulses:
        extra = []
        adversary = (p.get("adversary") or "").strip()
        if adversary:
            gid = matcher.lookup(adversary)
            if gid is None:
                hits = matcher.match(adversary)
                gid = hits[0].group_id if hits else None
            if gid is not None:
                extra.append((gid, "adversary_field", adversary))
        countries = [c for c in (iso2_from_name(x) for x in p.get("targeted_countries") or []) if c]
        indicators = p.get("indicators")
        ioc_count = len(indicators) if isinstance(indicators, list) else int(p.get("indicator_count") or 0)
        ev = store_activity(
            db,
            matcher,
            source_key="otx",
            source_type="otx",
            source_name=f"OTX · {p.get('author_name') or 'AlienVault'}",
            external_id=str(p["id"]),
            title=p.get("name") or "OTX pulse",
            summary=strip_html(p.get("description"), 1500),
            url=f"https://otx.alienvault.com/pulse/{p['id']}",
            published_at=_ts(p.get("created")),
            extra_group_ids=extra,
            countries=countries,
            sectors=[s.lower() for s in p.get("industries") or []],
            tags=(p.get("tags") or [])[:20],
            ioc_count=ioc_count,
        )
        if ev is not None:
            n += 1
    db.commit()
    return n


def run(db: Session) -> int:
    s = get_settings()
    matcher = GroupMatcher.from_db(db)

    def job(row: FeedStatus) -> int:
        if not s.otx_api_key:
            raise NotConfigured("Set ST_OTX_API_KEY to enable AlienVault OTX.")
        since = row.state.get("modified_since") or (
            datetime.now(timezone.utc) - timedelta(days=30)
        ).isoformat(timespec="seconds")
        started = datetime.now(timezone.utc).isoformat(timespec="seconds")
        n = 0
        with http_client(60) as c:
            url = f"{s.otx_base_url}/api/v1/pulses/subscribed"
            params = {"modified_since": since, "limit": 50, "page": 1}
            for _ in range(MAX_PAGES):
                r = c.get(url, params=params, headers={"X-OTX-API-KEY": s.otx_api_key})
                r.raise_for_status()
                data = r.json()
                n += ingest_pulses(db, matcher, data.get("results", []))
                if not data.get("next"):
                    break
                params["page"] += 1
        row.state = {**row.state, "modified_since": started}
        return n

    return run_tracked(db, "otx", "AlienVault OTX", "otx", job)
