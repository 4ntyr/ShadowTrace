"""Shape ORM rows into JSON-ready dicts shared across routers."""

from .countries import country_name
from .models import ActivityEvent, Group, GroupStateLink, MilitaryEvent


def country_ref(code: str | None) -> dict | None:
    return {"code": code, "name": country_name(code)} if code else None


def group_ref(g: Group) -> dict:
    return {
        "id": g.id,
        "slug": g.slug,
        "name": g.name,
        "kind": g.kind,
        "origin_country": country_ref(g.origin_country_code),
    }


def state_link(link: GroupStateLink) -> dict:
    return {
        "country": country_ref(link.country_code),
        "relation": link.relation,
        "agency": link.agency,
        "confidence": link.confidence,
        "origin": link.origin,
        "note": link.note,
        "source_name": link.source_name,
        "source_url": link.source_url,
    }


def activity(ev: ActivityEvent, groups_by_id: dict[int, Group] | None = None) -> dict:
    groups = []
    for gl in ev.group_links:
        g = (groups_by_id or {}).get(gl.group_id) or gl.group
        groups.append({**group_ref(g), "match_method": gl.match_method, "matched_text": gl.matched_text})
    return {
        "id": ev.id,
        "source_type": ev.source_type,
        "source_name": ev.source_name,
        "title": ev.title,
        "summary": ev.summary,
        "url": ev.url,
        "published_at": ev.published_at.isoformat(),
        "occurred_at": ev.occurred_at.isoformat() if ev.occurred_at else None,
        "countries": [country_ref(c) for c in ev.countries or []],
        "attributed_countries": [country_ref(c) for c in ev.attributed_countries or []],
        "sectors": ev.sectors or [],
        "tags": ev.tags or [],
        "effect": ev.effect,
        "ioc_count": ev.ioc_count,
        "groups": groups,
    }


def military(ev: MilitaryEvent) -> dict:
    return {
        "id": ev.id,
        "source": ev.source,
        "date": ev.event_date.isoformat(),
        "country": country_ref(ev.country_code),
        "location": ev.location,
        "lat": ev.lat,
        "lon": ev.lon,
        "event_type": ev.event_type,
        "sub_event_type": ev.sub_event_type,
        "actors": ev.actors,
        "fatalities": ev.fatalities,
        "description": ev.description,
        "url": ev.url,
        "intensity": round(ev.intensity, 3),
    }
