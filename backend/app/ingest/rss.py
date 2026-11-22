"""Vendor / CERT RSS connector. Keeps only items that mention a tracked group."""

import calendar
import logging
from datetime import datetime, timezone

import feedparser
from sqlalchemy.orm import Session

from ..util import strip_html
from .common import FeedStatus, http_client, run_tracked, store_activity
from .curation import load_feeds
from .matcher import GroupMatcher

log = logging.getLogger(__name__)


def _published(entry) -> datetime:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
    return datetime.now(timezone.utc)


def ingest_feed_content(db: Session, matcher: GroupMatcher, feed: dict, content: bytes) -> int:
    parsed = feedparser.parse(content)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"unparseable feed: {parsed.bozo_exception}")
    n = 0
    for e in parsed.entries:
        title = strip_html(e.get("title"), 500)
        summary = strip_html(e.get("summary") or e.get("description"), 1500)
        link = e.get("link")
        ext = e.get("id") or link or title
        tags = [t.get("term") for t in e.get("tags", []) if t.get("term")][:15]
        ev = store_activity(
            db,
            matcher,
            source_key=f"rss:{feed['key']}",
            source_type="rss",
            source_name=feed["name"],
            external_id=ext,
            title=title,
            summary=summary,
            url=link,
            published_at=_published(e),
            countries=feed.get("default_countries"),
            tags=tags,
        )
        if ev is not None:
            n += 1
    db.commit()
    return n


def run(db: Session) -> int:
    matcher = GroupMatcher.from_db(db)
    total = 0
    with http_client() as client:
        for feed in load_feeds():
            def job(_row: FeedStatus, feed=feed) -> int:
                r = client.get(feed["url"])
                r.raise_for_status()
                return ingest_feed_content(db, matcher, feed, r.content)

            total += run_tracked(db, f"rss:{feed['key']}", feed["name"], "rss", job)
    return total
