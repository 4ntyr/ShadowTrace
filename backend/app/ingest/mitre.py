"""MITRE ATT&CK (Enterprise) import.

`parse_bundle` turns the STIX 2.1 bundle into a compact snapshot (groups, techniques, software,
campaigns). A snapshot is committed at data/mitre_snapshot.json.gz so the app works offline;
the worker refreshes it from GitHub weekly.
"""

import gzip
import json
import logging
import re
from datetime import date, datetime

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import DATA_DIR, get_settings
from ..models import (
    Group,
    GroupAlias,
    GroupSoftware,
    GroupTechnique,
    HistoryEvent,
    Software,
    Technique,
)
from ..util import slugify

log = logging.getLogger(__name__)

SNAPSHOT_PATH = DATA_DIR / "mitre_snapshot.json.gz"

_CITATION = re.compile(r"\s*\(Citation:[^)]*\)")
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")


def clean_description(text: str | None) -> str:
    if not text:
        return ""
    text = _CITATION.sub("", text)
    text = _MD_LINK.sub(r"\1", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def _attack_id(obj: dict) -> str | None:
    for ref in obj.get("external_references", []):
        if ref.get("source_name") == "mitre-attack":
            return ref.get("external_id")
    return None


def _attack_url(obj: dict) -> str | None:
    for ref in obj.get("external_references", []):
        if ref.get("source_name") == "mitre-attack":
            return ref.get("url")
    return None


def _live(obj: dict) -> bool:
    return not obj.get("revoked") and not obj.get("x_mitre_deprecated")


def parse_bundle(bundle: dict) -> dict:
    objs = [o for o in bundle["objects"] if _live(o)]
    by_id = {o["id"]: o for o in objs}

    techniques = {}
    for o in objs:
        if o["type"] == "attack-pattern":
            aid = _attack_id(o)
            if aid:
                techniques[aid] = {
                    "name": o["name"],
                    "tactics": [p["phase_name"] for p in o.get("kill_chain_phases", [])],
                }

    software = {}
    for o in objs:
        if o["type"] in ("malware", "tool"):
            aid = _attack_id(o)
            if aid:
                desc = clean_description(o.get("description"))
                software[aid] = {"name": o["name"], "type": o["type"], "description": desc[:600]}

    groups = {}
    for o in objs:
        if o["type"] != "intrusion-set":
            continue
        aid = _attack_id(o)
        if not aid:
            continue
        aliases = [a for a in o.get("aliases", []) if a != o["name"]]
        groups[o["id"]] = {
            "attack_id": aid,
            "stix_id": o["id"],
            "name": o["name"],
            "aliases": aliases,
            "description": clean_description(o.get("description")),
            "created": o.get("created"),
            "modified": o.get("modified"),
            "first_seen": o.get("first_seen"),
            "url": _attack_url(o),
            "techniques": set(),
            "software": set(),
        }

    campaigns = {}
    for o in objs:
        if o["type"] == "campaign":
            campaigns[o["id"]] = {
                "attack_id": _attack_id(o),
                "name": o["name"],
                "description": clean_description(o.get("description")),
                "first_seen": o.get("first_seen"),
                "last_seen": o.get("last_seen"),
                "url": _attack_url(o),
                "groups": [],
            }

    for r in objs:
        if r["type"] != "relationship":
            continue
        src, tgt, rel = r.get("source_ref"), r.get("target_ref"), r.get("relationship_type")
        if src in groups and rel == "uses":
            t = by_id.get(tgt)
            if not t:
                continue
            tid = _attack_id(t)
            if t["type"] == "attack-pattern" and tid in techniques:
                groups[src]["techniques"].add(tid)
            elif t["type"] in ("malware", "tool") and tid in software:
                groups[src]["software"].add(tid)
        elif src in campaigns and rel == "attributed-to" and tgt in groups:
            campaigns[src]["groups"].append(groups[tgt]["attack_id"])

    out_groups = []
    for g in groups.values():
        g["techniques"] = sorted(g["techniques"])
        g["software"] = sorted(g["software"])
        out_groups.append(g)
    out_groups.sort(key=lambda g: g["attack_id"])

    return {
        "source": "MITRE ATT&CK Enterprise",
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "groups": out_groups,
        "techniques": techniques,
        "software": software,
        "campaigns": sorted(campaigns.values(), key=lambda c: c["attack_id"] or ""),
    }


def write_snapshot(snapshot: dict) -> None:
    with gzip.open(SNAPSHOT_PATH, "wt", encoding="utf-8") as f:
        json.dump(snapshot, f, separators=(",", ":"))


def load_snapshot() -> dict:
    with gzip.open(SNAPSHOT_PATH, "rt", encoding="utf-8") as f:
        return json.load(f)


def download_snapshot() -> dict:
    s = get_settings()
    with httpx.Client(timeout=300, headers={"User-Agent": s.http_user_agent}) as c:
        r = c.get(s.mitre_url, follow_redirects=True)
        r.raise_for_status()
        return parse_bundle(r.json())


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def import_snapshot(db: Session, snap: dict) -> dict:
    """Upsert MITRE data. Curated fields on groups are never overwritten here."""
    tech_rows = {t.attack_id: t for t in db.scalars(select(Technique))}
    for tid, t in snap["techniques"].items():
        row = tech_rows.get(tid)
        if row is None:
            db.add(Technique(attack_id=tid, name=t["name"], tactics=t["tactics"]))
        else:
            row.name, row.tactics = t["name"], t["tactics"]

    sw_rows = {s.attack_id: s for s in db.scalars(select(Software))}
    for sid, s in snap["software"].items():
        row = sw_rows.get(sid)
        if row is None:
            db.add(Software(attack_id=sid, name=s["name"], type=s["type"], description=s["description"]))
        else:
            row.name, row.type, row.description = s["name"], s["type"], s["description"]
    db.flush()

    existing = {g.attack_id: g for g in db.scalars(select(Group).where(Group.attack_id.is_not(None)))}
    by_slug = {g.slug: g for g in db.scalars(select(Group))}
    created = 0
    for g in snap["groups"]:
        row = existing.get(g["attack_id"])
        if row is None:
            slug = slugify(g["name"])
            # A curated-only group may already exist under this name; adopt it.
            row = by_slug.get(slug)
            if row is None:
                row = Group(slug=slug, name=g["name"], sources=[])
                db.add(row)
                created += 1
        row.attack_id = g["attack_id"]
        row.stix_id = g["stix_id"]
        row.mitre_url = g["url"]
        row.name = g["name"]
        row.description = g["description"]
        if row.first_seen is None:
            row.first_seen = _parse_date(g.get("first_seen"))
        if "mitre" not in (row.sources or []):
            row.sources = [*(row.sources or []), "mitre"]
        db.flush()

        have = {a.alias for a in row.aliases}
        for alias in g["aliases"]:
            if alias not in have:
                row.aliases.append(GroupAlias(alias=alias, source="mitre"))
                have.add(alias)

        db.execute(delete(GroupTechnique).where(GroupTechnique.group_id == row.id))
        db.execute(delete(GroupSoftware).where(GroupSoftware.group_id == row.id))
        for tid in g["techniques"]:
            db.add(GroupTechnique(group_id=row.id, technique_id=tid))
        for sid in g["software"]:
            db.add(GroupSoftware(group_id=row.id, software_id=sid))

    # Campaigns -> history events
    groups_by_aid = {g.attack_id: g for g in db.scalars(select(Group).where(Group.attack_id.is_not(None)))}
    db.execute(delete(HistoryEvent).where(HistoryEvent.origin == "mitre_campaign"))
    n_campaigns = 0
    for c in snap["campaigns"]:
        start = _parse_date(c.get("first_seen"))
        if start is None:
            continue
        for gaid in c["groups"]:
            grp = groups_by_aid.get(gaid)
            if grp is None:
                continue
            db.add(
                HistoryEvent(
                    group_id=grp.id,
                    date=start,
                    end_date=_parse_date(c.get("last_seen")),
                    date_precision="month",
                    title=c["name"],
                    description=c["description"],
                    kind="campaign",
                    origin="mitre_campaign",
                    source_name=f"MITRE ATT&CK {c['attack_id']}",
                    source_url=c["url"],
                )
            )
            n_campaigns += 1
    db.commit()
    return {"groups": len(snap["groups"]), "created": created, "campaign_events": n_campaigns}
