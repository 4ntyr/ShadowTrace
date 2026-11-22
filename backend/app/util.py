import re
import unicodedata
from datetime import date, datetime, timezone


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = value.replace("$", "s").replace("@", "at")
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "group"


def to_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def as_date(v) -> date | None:
    if v is None or isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    return date.fromisoformat(str(v)[:10])


def strip_html(text: str | None, limit: int = 1200) -> str:
    if not text:
        return ""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    import html

    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    return text[:limit]
