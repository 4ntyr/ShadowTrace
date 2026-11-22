"""GDELT 2.0 event connector (keyless, 15-minute updates).

GDELT is machine-coded from news and very noisy. Only events that look like military action are
kept: CAMEO force/bombing/mass-violence codes, located in an active conflict theatre, with a military
or rebel actor or a belligerent state as one of the actors, reported by >= N sources. Events are then
aggregated per (day, location, CAMEO root) so one strike reported 40 times becomes one row.
"""

import csv
import io
import logging
import math
import zipfile
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..countries import iso2_from_fips, load_countries
from ..models import MilitaryEvent
from .common import FeedStatus, active_conflicts, conflict_for, http_client, run_tracked

log = logging.getLogger(__name__)

# Column indexes in GDELT 2.0 export files (61 tab-separated columns).
C_DATE, C_A1NAME, C_A1CTRY, C_A1TYPE = 1, 6, 7, 12
C_A2NAME, C_A2CTRY, C_A2TYPE = 16, 17, 22
C_ROOTEVT, C_CODE, C_ROOT = 25, 26, 28
C_NSRC, C_NART = 32, 33
C_GEONAME, C_GEOCTRY, C_LAT, C_LON, C_FEATURE, C_URL = 52, 53, 56, 57, 58, 60

MILITARY_CODES = {
    "180": "Unconventional violence",
    "181": "Abduction",
    "183": "Bombing",
    "1831": "Suicide bombing",
    "1832": "Vehicle bombing",
    "1833": "Roadside bombing",
    "186": "Assassination",
    "190": "Conventional military force",
    "193": "Small-arms fighting",
    "194": "Artillery and tank fire",
    "195": "Aerial weapons",
    "1951": "Precision-guided aerial munitions",
    "1952": "Drone strike",
    "196": "Ceasefire violation",
    "200": "Mass violence",
    "201": "Mass expulsion",
    "202": "Mass killing",
    "203": "Ethnic cleansing",
    "204": "Weapons of mass destruction",
}
ROOT_TYPE = {"18": "Assault", "19": "Armed clash / strike", "20": "Mass violence"}
ROOT_WEIGHT = {"18": 0.45, "19": 0.55, "20": 0.8}
ARMED_ACTOR_TYPES = {"MIL", "REB", "SEP", "INS", "UAF"}


def _iso3_to_iso2() -> dict[str, str]:
    return {c["iso3"]: c["code"] for c in load_countries() if c["iso3"]}


def parse_export(content: bytes, conflicts, min_sources: int) -> dict[str, dict]:
    """Return aggregated candidate events keyed by external_id."""
    iso3 = _iso3_to_iso2()
    zf = zipfile.ZipFile(io.BytesIO(content))
    raw = zf.read(zf.namelist()[0]).decode("utf-8", errors="replace")
    out: dict[str, dict] = {}
    for row in csv.reader(io.StringIO(raw), delimiter="\t", quoting=csv.QUOTE_NONE):
        if len(row) < 61:
            continue
        code = row[C_CODE]
        if code not in MILITARY_CODES:
            continue
        try:
            nsrc = int(row[C_NSRC] or 0)
            nart = int(row[C_NART] or 0)
        except ValueError:
            continue
        if nsrc < min_sources:
            continue
        country = iso2_from_fips(row[C_GEOCTRY])
        day = datetime.strptime(row[C_DATE], "%Y%m%d").date()
        conflict = conflict_for(conflicts, country, day)
        if conflict is None:
            continue
        party_countries = {cc for p in conflict.parties for cc in p["countries"]}
        actor_countries = {iso3.get(row[C_A1CTRY]), iso3.get(row[C_A2CTRY])}
        armed = row[C_A1TYPE] in ARMED_ACTOR_TYPES or row[C_A2TYPE] in ARMED_ACTOR_TYPES
        if not armed and not (actor_countries & party_countries):
            continue
        root = row[C_ROOT]
        place = row[C_FEATURE] or row[C_GEONAME]
        key = f"{day.isoformat()}:{place}:{root}"
        agg = out.get(key)
        if agg is None:
            try:
                lat, lon = float(row[C_LAT]), float(row[C_LON])
            except ValueError:
                lat = lon = None
            actors = " → ".join(x for x in (row[C_A1NAME].title(), row[C_A2NAME].title()) if x)
            agg = out[key] = {
                "external_id": key,
                "conflict_id": conflict.id,
                "event_date": day,
                "country_code": country,
                "location": row[C_GEONAME],
                "lat": lat,
                "lon": lon,
                "event_type": ROOT_TYPE.get(root, "Military action"),
                "sub_event_type": MILITARY_CODES[code],
                "actors": actors or None,
                "url": row[C_URL],
                "articles": 0,
                "root": root,
            }
        agg["articles"] += nart
    for agg in out.values():
        # Severity grows with coverage, capped at 1.
        agg["intensity"] = min(1.0, ROOT_WEIGHT.get(agg["root"], 0.5) + math.log10(1 + agg["articles"]) / 6)
    return out


def upsert_events(db: Session, events: dict[str, dict]) -> int:
    n = 0
    for ev in events.values():
        row = db.scalar(
            select(MilitaryEvent).where(MilitaryEvent.source == "gdelt", MilitaryEvent.external_id == ev["external_id"])
        )
        desc = f"{ev['sub_event_type']} reported near {ev['location']} ({ev['articles']} articles)"
        if row is None:
            db.add(
                MilitaryEvent(
                    source="gdelt",
                    external_id=ev["external_id"],
                    conflict_id=ev["conflict_id"],
                    event_date=ev["event_date"],
                    country_code=ev["country_code"],
                    location=ev["location"],
                    lat=ev["lat"],
                    lon=ev["lon"],
                    event_type=ev["event_type"],
                    sub_event_type=ev["sub_event_type"],
                    actors=ev["actors"],
                    description=desc,
                    url=ev["url"],
                    intensity=ev["intensity"],
                )
            )
            n += 1
        else:
            row.intensity = max(row.intensity, ev["intensity"])
    db.commit()
    return n


def _file_urls(latest_ts: datetime, since_ts: datetime | None, backfill: int) -> list[tuple[str, str]]:
    stamps = []
    t = latest_ts
    while len(stamps) < backfill and (since_ts is None or t > since_ts):
        stamps.append(t)
        t -= timedelta(minutes=15)
    stamps.reverse()
    return [
        (s.strftime("%Y%m%d%H%M%S"), f"https://data.gdeltproject.org/gdeltv2/{s:%Y%m%d%H%M%S}.export.CSV.zip")
        for s in stamps
    ]


def run(db: Session) -> int:
    s = get_settings()

    def job(row: FeedStatus) -> int:
        if not s.gdelt_enabled:
            return 0
        conflicts = active_conflicts(db)
        if not conflicts:
            return 0
        with http_client(60) as c:
            r = c.get(s.gdelt_lastupdate_url.replace("http://", "https://"))
            r.raise_for_status()
            first = r.text.split("\n")[0].split()
            latest = datetime.strptime(first[2].rsplit("/", 1)[1][:14], "%Y%m%d%H%M%S")
            last = row.state.get("last_file")
            since = datetime.strptime(last, "%Y%m%d%H%M%S") if last else None
            n = 0
            for stamp, url in _file_urls(latest, since, s.gdelt_backfill_files):
                resp = c.get(url)
                if resp.status_code == 404:  # GDELT occasionally skips a slot
                    continue
                resp.raise_for_status()
                n += upsert_events(db, parse_export(resp.content, conflicts, s.gdelt_min_sources))
                row.state = {**row.state, "last_file": stamp}
                db.commit()
        return n

    return run_tracked(db, "gdelt", "GDELT 2.0 events", "gdelt", job)
