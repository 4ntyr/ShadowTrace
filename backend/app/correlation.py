"""Cyber ↔ kinetic correlation for the hybrid-warfare tracker.

For each conflict:
  1. Collect *conflict-relevant cyber events*: activity linked to a group (or state) aligned with a
     belligerent party, aimed at the theatre or a party (or with no known target).
  2. Collect kinetic events assigned to the conflict (ACLED, GDELT, curated).
  3. For every cyber event, score kinetic events within ±window days:

       score = time × geography × attribution × effect × date-basis × kinetic-severity

     and keep the best 3 above a threshold as "auto" HybridLinks. Curated links always win.
  4. Series helpers compute daily counts, a lagged cross-correlation (does cyber lead or follow
     kinetic activity?) and "convergence days" where both spike together.

Scores are triage aids for analysts, not attribution: temporal co-occurrence is not causation.
"""

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session, selectinload

from .models import ActivityEvent, ActivityGroup, Conflict, Group, GroupStateLink, HybridLink, MilitaryEvent

MIN_SCORE = 0.2
TOP_K = 3
EFFECT_WEIGHT = {"disruptive": 1.0, "ddos": 0.8, "influence": 0.7, "espionage": 0.5}
STATE_RELATIONS = ("operated_by", "sponsor", "aligned", "alleged", "attributed")


@dataclass
class CyberItem:
    event: ActivityEvent
    day: date
    basis: str  # occurred | reported
    sides: set[int]  # indexes into conflict.parties
    targets: set[str]


def _party_index(conflict: Conflict) -> dict[str, int]:
    return {cc: i for i, p in enumerate(conflict.parties) for cc in p["countries"]}


def _group_sides(db: Session, conflict: Conflict) -> dict[int, set[int]]:
    pidx = _party_index(conflict)
    sides: dict[int, set[int]] = defaultdict(set)
    for link in db.scalars(select(GroupStateLink).where(GroupStateLink.relation.in_(STATE_RELATIONS))):
        if link.country_code in pidx:
            sides[link.group_id].add(pidx[link.country_code])
    if conflict.extra_group_slugs:
        for g in db.scalars(select(Group).where(Group.slug.in_(conflict.extra_group_slugs))):
            sides.setdefault(g.id, set())  # participant even if side unknown
    return sides


def cyber_items(db: Session, conflict: Conflict, start: date, end: date) -> list[CyberItem]:
    pidx = _party_index(conflict)
    theatre = set(conflict.theatre_countries) | set(pidx)
    gsides = _group_sides(db, conflict)

    t0 = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    t1 = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    q = (
        select(ActivityEvent)
        .options(selectinload(ActivityEvent.group_links))
        .where(
            or_(
                and_(ActivityEvent.occurred_at.is_not(None), ActivityEvent.occurred_at >= t0, ActivityEvent.occurred_at < t1),
                and_(ActivityEvent.occurred_at.is_(None), ActivityEvent.published_at >= t0, ActivityEvent.published_at < t1),
            )
        )
    )
    items = []
    for ev in db.scalars(q):
        participant = False
        sides: set[int] = set()
        for gl in ev.group_links:
            if gl.group_id in gsides:
                participant = True
                sides |= gsides[gl.group_id]
        for cc in ev.attributed_countries or []:
            if cc in pidx:
                participant = True
                sides.add(pidx[cc])
        if conflict.slug in (ev.tags or []):
            participant = True
        if not participant:
            continue
        targets = set(ev.countries or [])
        if targets and not (targets & theatre) and conflict.slug not in (ev.tags or []):
            continue
        when = ev.occurred_at or ev.published_at
        items.append(
            CyberItem(ev, when.date(), "occurred" if ev.occurred_at else "reported", sides, targets)
        )
    return items


def score_pair(conflict: Conflict, item: CyberItem, kin: MilitaryEvent, pidx: dict[str, int]) -> tuple[float, str]:
    w = conflict.window_days
    lag = (item.day - kin.event_date).days
    time_f = 1 - abs(lag) / (w + 1)

    if not item.targets:
        geo_f, geo_txt = 0.6, "target country unknown"
    elif kin.country_code in item.targets:
        geo_f, geo_txt = 1.0, f"same country ({kin.country_code})"
    else:
        geo_f, geo_txt = 0.4, "different country in theatre"

    kin_side = pidx.get(kin.country_code or "")
    if item.sides and kin_side is not None and kin_side not in item.sides:
        attr_f, attr_txt = 1.0, "cyber actor aligned with the opposing party"
    elif item.sides and kin_side is not None:
        attr_f, attr_txt = 0.5, "cyber actor aligned with the same party as the location"
    else:
        attr_f, attr_txt = 0.7, "party alignment unclear"

    eff_f = EFFECT_WEIGHT.get(item.event.effect or "", 0.6)
    basis_f = 1.0 if item.basis == "occurred" else 0.7
    sev_f = 0.5 + 0.5 * (kin.intensity or 0.3)
    score = time_f * geo_f * attr_f * eff_f * basis_f * sev_f
    when = "same day" if lag == 0 else (f"{abs(lag)}d after" if lag > 0 else f"{abs(lag)}d before")
    rationale = (
        f"Cyber event {when} kinetic event; {geo_txt}; {attr_txt}; "
        f"effect: {item.event.effect or 'unknown'}; date basis: {item.basis}."
    )
    return round(score, 4), rationale


def correlate_conflict(db: Session, conflict: Conflict, today: date | None = None) -> int:
    today = today or datetime.now(timezone.utc).date()
    w = conflict.window_days
    end = min(conflict.end_date or today, today)
    items = cyber_items(db, conflict, conflict.start_date - timedelta(days=w), end + timedelta(days=w))
    kinetic = db.scalars(select(MilitaryEvent).where(MilitaryEvent.conflict_id == conflict.id)).all()
    by_day: dict[date, list[MilitaryEvent]] = defaultdict(list)
    for k in kinetic:
        by_day[k.event_date].append(k)
    pidx = _party_index(conflict)

    curated_pairs = set(
        db.execute(
            select(HybridLink.activity_id, HybridLink.military_event_id).where(
                HybridLink.conflict_id == conflict.id, HybridLink.method == "curated"
            )
        ).all()
    )
    db.execute(delete(HybridLink).where(HybridLink.conflict_id == conflict.id, HybridLink.method == "auto"))
    n = 0
    seen: set[tuple[int, int]] = set()
    for item in items:
        cands = []
        for d in range(-w, w + 1):
            for k in by_day.get(item.day - timedelta(days=d), []):
                s, why = score_pair(conflict, item, k, pidx)
                if s >= MIN_SCORE:
                    cands.append((s, k, why))
        cands.sort(key=lambda c: -c[0])
        for s, k, why in cands[:TOP_K]:
            pair = (item.event.id, k.id)
            if pair in curated_pairs or pair in seen:
                continue
            seen.add(pair)
            db.add(
                HybridLink(
                    conflict_id=conflict.id,
                    activity_id=item.event.id,
                    military_event_id=k.id,
                    method="auto",
                    lag_days=float((item.day - k.event_date).days),
                    score=s,
                    date_basis=item.basis,
                    rationale=why,
                )
            )
            n += 1
    db.commit()
    return n


def correlate_all(db: Session) -> int:
    return sum(correlate_conflict(db, c) for c in db.scalars(select(Conflict)))


# ─────────────────────────── series analytics ───────────────────────────


def daily_series(db: Session, conflict: Conflict, start: date, end: date) -> list[dict]:
    days = [(start + timedelta(days=i)) for i in range((end - start).days + 1)]
    cyber = defaultdict(int)
    for it in cyber_items(db, conflict, start, end):
        cyber[it.day] += 1
    kin_count = defaultdict(int)
    kin_fat = defaultdict(int)
    for k in db.scalars(
        select(MilitaryEvent).where(
            MilitaryEvent.conflict_id == conflict.id,
            MilitaryEvent.event_date >= start,
            MilitaryEvent.event_date <= end,
        )
    ):
        kin_count[k.event_date] += 1
        kin_fat[k.event_date] += k.fatalities or 0
    return [
        {"date": d.isoformat(), "cyber": cyber[d], "kinetic": kin_count[d], "fatalities": kin_fat[d]}
        for d in days
    ]


def _pearson(a: list[float], b: list[float]) -> float | None:
    n = len(a)
    if n < 5:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va == 0 or vb == 0:
        return None
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    return cov / math.sqrt(va * vb)


def lag_correlation(series: list[dict], max_lag: int = 7) -> list[dict]:
    """r(lag) = corr(cyber[t], kinetic[t + lag]). Positive lag ⇒ cyber leads kinetic."""
    c = [float(x["cyber"]) for x in series]
    k = [float(x["kinetic"]) for x in series]
    out = []
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            a, b = c[: len(c) - lag], k[lag:]
        else:
            a, b = c[-lag:], k[: len(k) + lag]
        r = _pearson(a, b)
        out.append({"lag": lag, "r": None if r is None else round(r, 3), "n": len(a)})
    return out


def convergence_days(series: list[dict], window: int = 14, z: float = 1.5) -> list[dict]:
    """Days where both cyber and kinetic counts exceed their trailing mean + z·σ."""
    out = []
    for i in range(window, len(series)):
        hist = series[i - window : i]
        flags = {}
        for key in ("cyber", "kinetic"):
            vals = [h[key] for h in hist]
            m = sum(vals) / window
            sd = math.sqrt(sum((v - m) ** 2 for v in vals) / window)
            flags[key] = series[i][key] > m + z * max(sd, 0.5) and series[i][key] > 0
        if flags["cyber"] and flags["kinetic"]:
            out.append(series[i])
    return out
