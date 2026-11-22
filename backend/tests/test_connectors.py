import io
import zipfile
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app import correlation
from app.ingest import acled, gdelt, otx, rss
from app.ingest.matcher import GroupMatcher
from app.models import ActivityEvent, Conflict, HybridLink, MilitaryEvent

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>Sandworm deploys new wiper against Ukrainian energy company</title>
<link>https://example.org/a</link><guid>a-1</guid><pubDate>{d}</pubDate>
<description>&lt;p&gt;The GRU unit hit a power utility in Ukraine.&lt;/p&gt;</description></item>
<item><title>Patch Tuesday roundup</title><link>https://example.org/b</link><guid>b-1</guid><pubDate>{d}</pubDate></item>
</channel></rss>"""


def _rfc822(dt):
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0000").encode()


def test_rss_ingest_keeps_only_group_mentions(db):
    now = datetime.now(timezone.utc)
    content = RSS.replace(b"{d}", _rfc822(now))
    m = GroupMatcher.from_db(db)
    n = rss.ingest_feed_content(db, m, {"key": "test", "name": "Test feed"}, content)
    assert n == 1
    ev = db.scalar(select(ActivityEvent).where(ActivityEvent.source_key == "rss:test"))
    assert ev.countries == ["UA"]  # RU (attacker origin) excluded
    assert ev.effect == "disruptive"
    assert "energy" in ev.sectors
    assert [gl.group.name for gl in ev.group_links] == ["Sandworm Team"]
    # duplicates are ignored
    assert rss.ingest_feed_content(db, m, {"key": "test", "name": "Test feed"}, content) == 0


def test_otx_pulse_uses_adversary_field(db):
    m = GroupMatcher.from_db(db)
    pulses = [{
        "id": "abc123", "name": "New phishing wave", "description": "credential phishing",
        "adversary": "Charming Kitten", "targeted_countries": ["Israel", "United States of America"],
        "industries": ["Government"], "tags": ["phishing"], "indicators": [{"x": 1}, {"x": 2}],
        "created": "2026-11-01T10:00:00.000", "author_name": "AlienVault",
    }]
    assert otx.ingest_pulses(db, m, pulses) == 1
    ev = db.scalar(select(ActivityEvent).where(ActivityEvent.source_key == "otx", ActivityEvent.external_id == "abc123"))
    assert ev.countries[:2] == ["IL", "US"]
    assert ev.ioc_count == 2
    assert ev.group_links[0].group.name == "Magic Hound"
    assert ev.group_links[0].match_method == "adversary_field"


def _gdelt_zip(rows):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("x.export.CSV", "\n".join("\t".join(r) for r in rows))
    return buf.getvalue()


def _row(day, code, root, fips, a1type="MIL", a1ctry="RUS", a2ctry="UKR", nsrc="3", nart="5", place="Kharkiv, Ukraine", feat="-1"):
    r = [""] * 61
    r[1] = day
    r[6], r[7], r[12] = "RUSSIA", a1ctry, a1type
    r[16], r[17] = "UKRAINE", a2ctry
    r[25], r[26], r[28] = "1", code, root
    r[32], r[33] = nsrc, nart
    r[52], r[53], r[56], r[57], r[58] = place, fips, "49.98", "36.25", feat
    r[60] = "https://news.example/x"
    return r


def test_gdelt_parse_filters_and_aggregates(db):
    ru = db.scalar(select(Conflict).where(Conflict.slug == "russia-ukraine-war"))
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    content = _gdelt_zip([
        _row(day, "195", "19", "UP"),
        _row(day, "195", "19", "UP", nart="7"),          # same day/place/root → aggregated
        _row(day, "190", "19", "US", place="Dallas"),     # outside theatre
        _row(day, "010", "01", "UP"),                     # not a military code
        _row(day, "190", "19", "UP", a1type="", a1ctry="FRA", a2ctry="DEU", place="Lviv", feat="9"),  # no armed/party actor
    ])
    out = gdelt.parse_export(content, [ru], min_sources=1)
    assert len(out) == 1
    ev = next(iter(out.values()))
    assert ev["articles"] == 12 and ev["country_code"] == "UA"
    assert ev["sub_event_type"] == "Aerial weapons"


def test_acled_records(db):
    ru = db.scalar(select(Conflict).where(Conflict.slug == "russia-ukraine-war"))
    d = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    recs = [
        {"event_id_cnty": "UKR999", "event_date": d, "event_type": "Explosions/Remote violence",
         "sub_event_type": "Shelling/artillery/missile attack", "actor1": "Military Forces of Russia",
         "actor2": "Civilians (Ukraine)", "location": "Kharkiv", "latitude": "49.98", "longitude": "36.25",
         "fatalities": "4", "notes": "Shelling of Kharkiv"},
        {"event_id_cnty": "UKR1000", "event_date": d, "event_type": "Protests"},
    ]
    assert acled.ingest_records(db, recs, [ru], "UA") == 1
    assert acled.ingest_records(db, recs, [ru], "UA") == 0
    assert 0.6 < acled.intensity("Explosions/Remote violence", 4) <= 1.0


def test_correlation_links_and_series(db):
    ru = db.scalar(select(Conflict).where(Conflict.slug == "russia-ukraine-war"))
    today = datetime.now(timezone.utc).date()
    kin = MilitaryEvent(source="curated", external_id="test:strike", conflict_id=ru.id, event_date=today - timedelta(days=2),
                        country_code="UA", event_type="Explosions/Remote violence", description="Strike", intensity=0.9)
    db.add(kin)
    db.commit()
    m = GroupMatcher.from_db(db)
    rss.ingest_feed_content(db, m, {"key": "corr", "name": "Corr"},
                            RSS.replace(b"{d}", _rfc822(datetime.now(timezone.utc) - timedelta(days=1))).replace(b"a-1", b"corr-1"))
    n = correlation.correlate_conflict(db, ru, today)
    assert n >= 1
    cyber = db.scalar(select(ActivityEvent).where(ActivityEvent.external_id == "corr-1"))
    link = db.scalar(select(HybridLink).where(HybridLink.military_event_id == kin.id, HybridLink.activity_id == cyber.id))
    assert link.method == "auto" and link.date_basis == "reported"
    assert link.lag_days == 1.0
    assert "opposing party" in link.rationale

    series = correlation.daily_series(db, ru, today - timedelta(days=30), today)
    assert len(series) == 31
    lags = correlation.lag_correlation(series, 3)
    assert [l["lag"] for l in lags] == [-3, -2, -1, 0, 1, 2, 3]
    # curated links survive re-correlation
    assert db.scalar(select(HybridLink).where(HybridLink.method == "curated")) is not None


def test_lag_correlation_detects_lead():
    # cyber spikes exactly 2 days before kinetic spikes
    base = [0] * 40
    cyber, kin = base[:], base[:]
    for i in (5, 15, 25):
        cyber[i] = 5
        kin[i + 2] = 5
    series = [{"date": str(i), "cyber": c, "kinetic": k} for i, (c, k) in enumerate(zip(cyber, kin))]
    best = max(correlation.lag_correlation(series, 4), key=lambda x: x["r"] or -1)
    assert best["lag"] == 2
