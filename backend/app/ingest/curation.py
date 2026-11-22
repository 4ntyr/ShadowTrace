"""Load curated YAML (groups, conflicts) and reference data into the database.

Idempotent: running it repeatedly converges the DB to the YAML. Curated rows are identified by
origin/source="curated" so MITRE and feed data are left untouched.
"""

import logging
from datetime import date, datetime, time, timezone

import yaml
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..config import DATA_DIR
from ..countries import load_countries, valid_codes
from ..models import (
    ActivityEvent,
    ActivityGroup,
    Conflict,
    Country,
    Group,
    GroupAlias,
    GroupRelation,
    GroupStateLink,
    HistoryEvent,
    HybridLink,
    MilitaryEvent,
)
from ..util import as_date, slugify
from .attribution import extract_countries, is_criminal

log = logging.getLogger(__name__)
CURATION_DIR = DATA_DIR / "curation"


def _load_yaml(name: str) -> dict:
    with open(CURATION_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_feeds() -> list[dict]:
    return _load_yaml("feeds.yaml").get("feeds", [])


def seed_countries(db: Session) -> None:
    have = {c.code: c for c in db.scalars(select(Country))}
    for c in load_countries():
        row = have.get(c["code"])
        if row is None:
            db.add(Country(**c))
        else:
            row.name, row.iso3, row.numeric, row.alt_names = c["name"], c["iso3"], c["numeric"], c["alt_names"]
    db.commit()


def find_group(db: Session, name: str) -> Group | None:
    """Find by exact name, slug or alias (case-insensitive)."""
    lname = name.lower()
    for g in db.scalars(select(Group).where(Group.slug == slugify(name))):
        return g
    for g in db.scalars(select(Group)):
        if g.name.lower() == lname:
            return g
    alias = db.scalars(select(GroupAlias).where(func.lower(GroupAlias.alias) == lname)).first()
    return alias.group if alias else None


def _check_country(code: str, where: str) -> str:
    if code not in valid_codes():
        raise ValueError(f"Unknown country code {code!r} in {where}")
    return code


def apply_group_curation(db: Session) -> dict:
    data = _load_yaml("groups.yaml").get("groups", [])
    stats = {"groups": 0, "created": 0, "relations": 0, "history": 0}

    db.execute(delete(GroupStateLink))
    db.execute(delete(GroupRelation))
    db.execute(delete(HistoryEvent).where(HistoryEvent.origin == "curated"))
    db.flush()

    resolved: dict[str, Group] = {}
    for entry in data:
        g = find_group(db, entry["match"])
        if g is None:
            name = entry.get("name", entry["match"])
            g = Group(slug=slugify(name), name=name, sources=[], description="")
            db.add(g)
            db.flush()
            if name != entry["match"]:
                g.aliases.append(GroupAlias(alias=entry["match"], source="curated"))
            stats["created"] += 1
        if "curated" not in (g.sources or []):
            g.sources = [*(g.sources or []), "curated"]
        g.summary = (entry.get("summary") or "").strip() or None
        g.motivation = entry.get("motivation")
        g.kind = entry.get("kind", "apt")
        g.target_countries = [_check_country(c, entry["match"]) for c in entry.get("target_countries", [])]
        g.target_sectors = entry.get("target_sectors", [])
        if entry.get("first_seen"):
            g.first_seen = as_date(entry["first_seen"])
        for alias in entry.get("aliases", []):
            if alias not in {a.alias for a in g.aliases}:
                g.aliases.append(GroupAlias(alias=alias, source="curated"))

        primary = None
        for s in entry.get("states", []):
            code = _check_country(s["country"], entry["match"])
            db.add(
                GroupStateLink(
                    group_id=g.id,
                    country_code=code,
                    relation=s["relation"],
                    agency=s.get("agency"),
                    confidence=s.get("confidence", "medium"),
                    note=s.get("note"),
                    source_name=s.get("source_name"),
                    source_url=s.get("source_url"),
                )
            )
            if primary is None and s["relation"] in ("operated_by", "sponsor", "aligned"):
                primary = code
            elif primary is None:
                primary = code
        g.origin_country_code = primary

        for h in entry.get("history", []):
            db.add(
                HistoryEvent(
                    group_id=g.id,
                    date=as_date(h["date"]),
                    date_precision=h.get("precision", "day"),
                    title=h["title"],
                    description=(h.get("description") or "").strip(),
                    kind=h.get("kind", "operation"),
                    origin="curated",
                    source_name=h.get("source_name"),
                    source_url=h.get("source_url"),
                )
            )
            stats["history"] += 1
        resolved[entry["match"]] = g
        stats["groups"] += 1
    db.flush()
    stats["extracted_links"] = _apply_extracted_attribution(db, {g.id for g in resolved.values()})

    for entry in data:
        src = resolved[entry["match"]]
        for r in entry.get("relations", []):
            tgt = resolved.get(r["target"]) or find_group(db, r["target"])
            if tgt is None:
                log.warning("relation target %r not found (from %s)", r["target"], entry["match"])
                continue
            db.add(
                GroupRelation(
                    source_group_id=src.id,
                    target_group_id=tgt.id,
                    relation=r["type"],
                    description=r.get("description"),
                    confidence=r.get("confidence", "medium"),
                    source_name=r.get("source_name"),
                    source_url=r.get("source_url"),
                )
            )
            stats["relations"] += 1
    db.commit()
    return stats


def _apply_extracted_attribution(db: Session, curated_ids: set[int]) -> int:
    """State links parsed from MITRE descriptions for groups without curated attribution."""
    n = 0
    for g in db.scalars(select(Group).where(Group.attack_id.is_not(None))):
        if g.id in curated_ids:
            continue
        criminal = is_criminal(g.description)
        if criminal and g.kind == "apt":
            g.kind = "criminal"
            g.motivation = g.motivation or "financial"
        codes = extract_countries(g.description)
        for code in codes:
            db.add(
                GroupStateLink(
                    group_id=g.id,
                    country_code=code,
                    relation="based_in" if criminal else "attributed",
                    confidence="low",
                    origin="mitre_text",
                    note="Auto-extracted from the MITRE ATT&CK description; not analyst-reviewed.",
                    source_name="MITRE ATT&CK",
                    source_url=g.mitre_url,
                )
            )
            n += 1
        g.origin_country_code = codes[0] if codes else None
    return n


def _dt(d) -> datetime:
    return datetime.combine(as_date(d), time(12, 0), tzinfo=timezone.utc)


def apply_conflict_curation(db: Session) -> dict:
    data = _load_yaml("conflicts.yaml").get("conflicts", [])
    stats = {"conflicts": 0, "cyber": 0, "kinetic": 0, "links": 0}
    existing = {c.slug: c for c in db.scalars(select(Conflict))}

    for entry in data:
        c = existing.get(entry["slug"]) or Conflict(slug=entry["slug"])
        c.name = entry["name"]
        c.description = (entry.get("description") or "").strip()
        c.status = entry.get("status", "active")
        c.start_date = as_date(entry["start"])
        c.end_date = as_date(entry.get("end"))
        c.theatre_countries = [_check_country(x, entry["slug"]) for x in entry.get("theatre", [])]
        c.parties = [
            {"name": p["name"], "countries": [_check_country(x, entry["slug"]) for x in p["countries"]]}
            for p in entry.get("parties", [])
        ]
        c.extra_group_slugs = []
        for name in entry.get("groups", []):
            g = find_group(db, name)
            if g:
                c.extra_group_slugs.append(g.slug)
            else:
                log.warning("conflict %s: group %r not found", entry["slug"], name)
        c.window_days = entry.get("window_days", 3)
        db.add(c)
        db.flush()
        stats["conflicts"] += 1

        cyber_ids: dict[str, int] = {}
        for ev in entry.get("cyber_events", []):
            ext = f"{entry['slug']}:{ev['key']}"
            row = db.scalars(
                select(ActivityEvent).where(
                    ActivityEvent.source_key == "curated", ActivityEvent.external_id == ext
                )
            ).first() or ActivityEvent(source_key="curated", external_id=ext)
            row.source_type = "curated"
            row.source_name = ev.get("source_name") or "ShadowTrace curation"
            row.title = ev["title"]
            row.summary = (ev.get("summary") or "").strip()
            row.url = ev.get("url")
            row.published_at = _dt(ev["date"])
            row.occurred_at = _dt(ev["date"])
            row.countries = [_check_country(x, ext) for x in ev.get("countries", [])]
            row.attributed_countries = [_check_country(x, ext) for x in ev.get("attributed", [])]
            row.sectors = ev.get("sectors", [])
            row.tags = ["hybrid", entry["slug"]]
            row.effect = ev.get("effect")
            db.add(row)
            db.flush()
            row.group_links.clear()
            db.flush()
            for gname in ev.get("groups", []):
                g = find_group(db, gname)
                if g:
                    row.group_links.append(
                        ActivityGroup(group_id=g.id, match_method="curated", matched_text=gname)
                    )
            cyber_ids[ev["key"]] = row.id
            stats["cyber"] += 1

        kinetic_ids: dict[str, int] = {}
        for ev in entry.get("kinetic_events", []):
            ext = f"{entry['slug']}:{ev['key']}"
            row = db.scalars(
                select(MilitaryEvent).where(
                    MilitaryEvent.source == "curated", MilitaryEvent.external_id == ext
                )
            ).first() or MilitaryEvent(source="curated", external_id=ext)
            row.conflict_id = c.id
            row.event_date = as_date(ev["date"])
            row.country_code = _check_country(ev["country"], ext)
            row.location = ev.get("location")
            row.lat, row.lon = ev.get("lat"), ev.get("lon")
            row.event_type = ev.get("type", "Battles")
            row.description = ev["title"]
            row.fatalities = ev.get("fatalities")
            row.intensity = float(ev.get("intensity", 0.5))
            row.url = ev.get("url")
            db.add(row)
            db.flush()
            kinetic_ids[ev["key"]] = row.id
            stats["kinetic"] += 1

        db.execute(delete(HybridLink).where(HybridLink.conflict_id == c.id, HybridLink.method == "curated"))
        for link in entry.get("links", []):
            a, m = cyber_ids[link["cyber"]], kinetic_ids[link["kinetic"]]
            cyber = db.get(ActivityEvent, a)
            kin = db.get(MilitaryEvent, m)
            # An auto link for the same pair is superseded by the curated one.
            db.execute(delete(HybridLink).where(HybridLink.activity_id == a, HybridLink.military_event_id == m))
            lag = (cyber.occurred_at.date() - kin.event_date).days
            db.add(
                HybridLink(
                    conflict_id=c.id,
                    activity_id=a,
                    military_event_id=m,
                    method="curated",
                    lag_days=float(lag),
                    score=1.0,
                    date_basis="occurred",
                    rationale=link.get("rationale", ""),
                )
            )
            stats["links"] += 1
    db.commit()
    return stats


def ensure_date(d) -> date:
    return as_date(d)
