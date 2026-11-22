"""ACLED connector (Armed Conflict Location & Event Data).

ACLED requires free registration. Since 2025 its API uses OAuth (password grant) at
https://acleddata.com/oauth/token and serves data from /api/acled/read. Set ST_ACLED_USERNAME and
ST_ACLED_PASSWORD; the connector is skipped (and shown as "not configured") otherwise.
"""

import math
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..countries import country_name
from ..models import MilitaryEvent
from .common import FeedStatus, NotConfigured, active_conflicts, conflict_for, http_client, run_tracked

KEEP_TYPES = {
    "Battles": 0.5,
    "Explosions/Remote violence": 0.6,
    "Violence against civilians": 0.5,
    "Strategic developments": 0.25,
}
PAGE_SIZE = 5000
MAX_PAGES = 10


def intensity(event_type: str, fatalities: int | None) -> float:
    base = KEEP_TYPES.get(event_type, 0.3)
    return min(1.0, base + math.log10(1 + (fatalities or 0)) / 3)


def ingest_records(db: Session, records: list[dict], conflicts, iso2: str) -> int:
    n = 0
    for r in records:
        etype = r.get("event_type")
        if etype not in KEEP_TYPES:
            continue
        day = date.fromisoformat(r["event_date"][:10])
        conflict = conflict_for(conflicts, iso2, day)
        if conflict is None:
            continue
        ext = str(r.get("event_id_cnty") or r.get("event_id"))
        if db.scalar(select(MilitaryEvent.id).where(MilitaryEvent.source == "acled", MilitaryEvent.external_id == ext)):
            continue
        fat = int(r.get("fatalities") or 0)
        try:
            lat, lon = float(r.get("latitude")), float(r.get("longitude"))
        except (TypeError, ValueError):
            lat = lon = None
        actors = " → ".join(x for x in (r.get("actor1"), r.get("actor2")) if x)
        db.add(
            MilitaryEvent(
                source="acled",
                external_id=ext,
                conflict_id=conflict.id,
                event_date=day,
                country_code=iso2,
                location=r.get("location"),
                lat=lat,
                lon=lon,
                event_type=etype,
                sub_event_type=r.get("sub_event_type"),
                actors=actors[:500] or None,
                fatalities=fat,
                description=(r.get("notes") or "")[:2000],
                url=None,
                intensity=intensity(etype, fat),
            )
        )
        n += 1
    db.commit()
    return n


def run(db: Session) -> int:
    s = get_settings()

    def job(row: FeedStatus) -> int:
        if not (s.acled_username and s.acled_password):
            raise NotConfigured("Set ST_ACLED_USERNAME and ST_ACLED_PASSWORD to enable ACLED.")
        conflicts = active_conflicts(db)
        countries = sorted({c for k in conflicts for c in k.theatre_countries})
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=s.acled_lookback_days)
        n = 0
        with http_client(120) as c:
            tok = c.post(
                f"{s.acled_base_url}/oauth/token",
                data={
                    "username": s.acled_username,
                    "password": s.acled_password,
                    "grant_type": "password",
                    "client_id": "acled",
                },
            )
            tok.raise_for_status()
            headers = {"Authorization": f"Bearer {tok.json()['access_token']}"}
            for iso2 in countries:
                for page in range(1, MAX_PAGES + 1):
                    r = c.get(
                        f"{s.acled_base_url}/api/acled/read",
                        params={
                            "_format": "json",
                            "country": country_name(iso2),
                            "event_date": f"{start.isoformat()}|{end.isoformat()}",
                            "event_date_where": "BETWEEN",
                            "limit": PAGE_SIZE,
                            "page": page,
                        },
                        headers=headers,
                    )
                    r.raise_for_status()
                    data = r.json().get("data", [])
                    n += ingest_records(db, data, conflicts, iso2)
                    if len(data) < PAGE_SIZE:
                        break
        row.state = {**row.state, "last_window": [start.isoformat(), end.isoformat()]}
        return n

    return run_tracked(db, "acled", "ACLED conflict events", "acled", job)
