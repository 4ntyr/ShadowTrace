"""Database schema.

Core entities
  Group          an APT / state-linked threat actor (seeded from MITRE ATT&CK, enriched by curation)
  Country        ISO 3166 country; used for sponsors, targets and conflict theatres
  GroupStateLink group <-> state (sponsor / operated-by / aligned / alleged) with confidence
  GroupRelation  group <-> group (subgroup, overlap, shared tooling, collaboration, ...)
  HistoryEvent   dated milestones in a group's history (MITRE campaigns + curated)
  ActivityEvent  a reported cyber activity item (RSS article, OTX pulse, curated incident)
  MilitaryEvent  a kinetic/military event (ACLED, GDELT, curated)
  Conflict       a theatre in which cyber and kinetic activity are correlated
  HybridLink     a scored pairing of a cyber event with a kinetic event in a conflict
"""

import datetime as _dt
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(100))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    favourites: Mapped[list["Favourite"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Country(Base):
    __tablename__ = "countries"

    code: Mapped[str] = mapped_column(String(2), primary_key=True)  # ISO 3166-1 alpha-2
    iso3: Mapped[str | None] = mapped_column(String(3))
    numeric: Mapped[str | None] = mapped_column(String(3))
    name: Mapped[str] = mapped_column(String(120))
    alt_names: Mapped[list] = mapped_column(JSON, default=list)


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    attack_id: Mapped[str | None] = mapped_column(String(16), unique=True)
    stix_id: Mapped[str | None] = mapped_column(String(80))
    mitre_url: Mapped[str | None] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str | None] = mapped_column(Text)  # curated one-paragraph profile
    motivation: Mapped[str | None] = mapped_column(String(40))  # espionage, financial, destructive, ...
    kind: Mapped[str] = mapped_column(String(30), default="apt")  # apt, hacktivist, criminal, persona
    origin_country_code: Mapped[str | None] = mapped_column(ForeignKey("countries.code"))
    first_seen: Mapped[date | None] = mapped_column(Date)
    target_countries: Mapped[list] = mapped_column(JSON, default=list)
    target_sectors: Mapped[list] = mapped_column(JSON, default=list)
    sources: Mapped[list] = mapped_column(JSON, default=list)  # ["mitre", "curated"]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    origin_country: Mapped[Country | None] = relationship()
    aliases: Mapped[list["GroupAlias"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    state_links: Mapped[list["GroupStateLink"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    history: Mapped[list["HistoryEvent"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    techniques: Mapped[list["Technique"]] = relationship(secondary="group_techniques")
    software: Mapped[list["Software"]] = relationship(secondary="group_software")


class GroupAlias(Base):
    __tablename__ = "group_aliases"
    __table_args__ = (UniqueConstraint("group_id", "alias"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    alias: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(40), default="mitre")

    group: Mapped[Group] = relationship(back_populates="aliases")


class GroupStateLink(Base):
    __tablename__ = "group_state_links"
    __table_args__ = (UniqueConstraint("group_id", "country_code", "relation"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    country_code: Mapped[str] = mapped_column(ForeignKey("countries.code"))
    # operated_by | sponsor | aligned | alleged (curated); attributed | based_in (auto-extracted)
    relation: Mapped[str] = mapped_column(String(30))
    origin: Mapped[str] = mapped_column(String(20), default="curated")  # curated | mitre_text
    agency: Mapped[str | None] = mapped_column(String(200))
    # confirmed (government attribution/indictment) | high | medium | low
    confidence: Mapped[str] = mapped_column(String(20), default="medium")
    note: Mapped[str | None] = mapped_column(Text)
    source_name: Mapped[str | None] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(500))

    group: Mapped[Group] = relationship(back_populates="state_links")
    country: Mapped[Country] = relationship()


class GroupRelation(Base):
    __tablename__ = "group_relations"
    __table_args__ = (UniqueConstraint("source_group_id", "target_group_id", "relation"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    target_group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    # subgroup | overlap | collaboration | shared_tooling | same_agency | successor
    relation: Mapped[str] = mapped_column(String(30))
    description: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(20), default="medium")
    source_name: Mapped[str | None] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(500))

    source_group: Mapped[Group] = relationship(foreign_keys=[source_group_id])
    target_group: Mapped[Group] = relationship(foreign_keys=[target_group_id])


class Technique(Base):
    __tablename__ = "techniques"

    attack_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    tactics: Mapped[list] = mapped_column(JSON, default=list)


class GroupTechnique(Base):
    __tablename__ = "group_techniques"

    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )
    technique_id: Mapped[str] = mapped_column(
        ForeignKey("techniques.attack_id", ondelete="CASCADE"), primary_key=True
    )


class Software(Base):
    __tablename__ = "software"

    attack_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(20))  # malware | tool
    description: Mapped[str] = mapped_column(Text, default="")


class GroupSoftware(Base):
    __tablename__ = "group_software"

    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )
    software_id: Mapped[str] = mapped_column(
        ForeignKey("software.attack_id", ondelete="CASCADE"), primary_key=True
    )


class HistoryEvent(Base):
    __tablename__ = "history_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    date: Mapped[_dt.date] = mapped_column(Date)
    end_date: Mapped[_dt.date | None] = mapped_column(Date)
    date_precision: Mapped[str] = mapped_column(String(10), default="day")  # day | month | year
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    # campaign | operation | disclosure | indictment | sanction | milestone
    kind: Mapped[str] = mapped_column(String(30), default="campaign")
    origin: Mapped[str] = mapped_column(String(30), default="curated")  # curated | mitre_campaign
    source_name: Mapped[str | None] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(500))

    group: Mapped[Group] = relationship(back_populates="history")


class ActivityEvent(Base):
    """A reported piece of cyber activity.

    `published_at` is when the item was reported; `occurred_at` is when the activity actually
    took place, which is only known for curated items (and some OTX pulses). Correlation uses
    occurred_at when available and marks report-date based matches as lower confidence.
    """

    __tablename__ = "activity_events"
    __table_args__ = (
        UniqueConstraint("source_key", "external_id"),
        Index("ix_activity_published", "published_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(80))  # e.g. rss:welivesecurity, otx, curated
    source_type: Mapped[str] = mapped_column(String(20))  # rss | otx | curated
    source_name: Mapped[str] = mapped_column(String(200))
    external_id: Mapped[str] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(500))
    summary: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str | None] = mapped_column(String(1000))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    countries: Mapped[list] = mapped_column(JSON, default=list)  # targeted ISO2 codes
    # States the activity is attributed to when no specific group is named (e.g. "Russia")
    attributed_countries: Mapped[list] = mapped_column(JSON, default=list)
    sectors: Mapped[list] = mapped_column(JSON, default=list)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    # disruptive | espionage | influence | ddos | unknown
    effect: Mapped[str | None] = mapped_column(String(30))
    ioc_count: Mapped[int] = mapped_column(Integer, default=0)

    group_links: Mapped[list["ActivityGroup"]] = relationship(
        back_populates="activity", cascade="all, delete-orphan"
    )


class ActivityGroup(Base):
    __tablename__ = "activity_groups"

    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activity_events.id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    match_method: Mapped[str] = mapped_column(String(30))  # alias | adversary_field | curated
    matched_text: Mapped[str | None] = mapped_column(String(200))

    activity: Mapped[ActivityEvent] = relationship(back_populates="group_links")
    group: Mapped[Group] = relationship()


class Favourite(Base):
    __tablename__ = "favourites"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="favourites")
    group: Mapped[Group] = relationship()


class Conflict(Base):
    __tablename__ = "conflicts"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | historical
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    theatre_countries: Mapped[list] = mapped_column(JSON, default=list)
    # [{"name": "Russia", "countries": ["RU"]}, {"name": "Ukraine", "countries": ["UA"]}]
    parties: Mapped[list] = mapped_column(JSON, default=list)
    extra_group_slugs: Mapped[list] = mapped_column(JSON, default=list)
    window_days: Mapped[int] = mapped_column(Integer, default=3)


class MilitaryEvent(Base):
    __tablename__ = "military_events"
    __table_args__ = (
        UniqueConstraint("source", "external_id"),
        Index("ix_military_date_country", "event_date", "country_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(20))  # acled | gdelt | curated
    external_id: Mapped[str] = mapped_column(String(200))
    conflict_id: Mapped[int | None] = mapped_column(
        ForeignKey("conflicts.id", ondelete="SET NULL"), index=True
    )
    event_date: Mapped[date] = mapped_column(Date)
    country_code: Mapped[str | None] = mapped_column(String(2))
    location: Mapped[str | None] = mapped_column(String(300))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    event_type: Mapped[str] = mapped_column(String(120))
    sub_event_type: Mapped[str | None] = mapped_column(String(120))
    actors: Mapped[str | None] = mapped_column(String(500))
    fatalities: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str | None] = mapped_column(String(1000))
    intensity: Mapped[float] = mapped_column(Float, default=0.3)  # 0..1, normalised severity
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HybridLink(Base):
    __tablename__ = "hybrid_links"
    __table_args__ = (UniqueConstraint("activity_id", "military_event_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    conflict_id: Mapped[int] = mapped_column(ForeignKey("conflicts.id", ondelete="CASCADE"), index=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activity_events.id", ondelete="CASCADE"))
    military_event_id: Mapped[int] = mapped_column(
        ForeignKey("military_events.id", ondelete="CASCADE")
    )
    method: Mapped[str] = mapped_column(String(20))  # curated | auto
    lag_days: Mapped[float] = mapped_column(Float)  # cyber date minus kinetic date
    score: Mapped[float] = mapped_column(Float)
    date_basis: Mapped[str] = mapped_column(String(20))  # occurred | reported
    rationale: Mapped[str] = mapped_column(Text, default="")
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    activity: Mapped[ActivityEvent] = relationship()
    military_event: Mapped[MilitaryEvent] = relationship()


class FeedStatus(Base):
    __tablename__ = "feed_status"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20))  # rss | otx | acled | gdelt | mitre | correlation
    configured: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    items_last_run: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[dict] = mapped_column(JSON, default=dict)  # connector cursor, e.g. last GDELT file
