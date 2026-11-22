"""Match free text (news headlines, report summaries) to tracked groups via names and aliases.

Precision matters more than recall here: a false match pollutes a group's activity feed and the
hybrid correlator. Rules:
  * word-boundary matches only; aliases shorter than 4 characters are ignored
  * aliases that are ordinary words ("Snake", "Play", "Sidewinder", "Reaper", ...) must appear with
    their original capitalisation AND next to an actor keyword ("Snake malware", "Play ransomware",
    "the Equation Group", "APT Sidewinder")
  * "X Group" / "X Team" names also match the bare stem "X" (Lazarus, Sandworm, Gamaredon)
"""

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import Group

AMBIGUOUS = {
    "akira", "armageddon", "axiom", "buckeye", "chimera", "cicada", "cleaver", "confucius",
    "dragonfly", "elfin", "equation", "ghostwriter", "inception", "karma", "krypton", "leviathan",
    "machete", "mantis", "mercury", "mirage", "monsoon", "newscaster", "nickel", "phosphorus",
    "play", "rancor", "rattlesnake", "reaper", "silence", "silicon", "sidewinder", "snake",
    "strider", "tick", "windigo", "zinc", "patchwork", "lyceum", "whitefly", "blackfly",
    "swallowtail", "springtail", "bitter", "moafee", "rocke", "carbanak", "radium", "molerats",
    "inception", "the dukes", "gallium", "platinum", "chromium", "bismuth", "potassium", "it army",
    # stems of "X Group" / "X Team" names and other common words
    "comment", "cobalt", "medusa", "beijing", "poseidon", "callisto", "gorgon", "tonto", "tsar",
    "hangover", "sunshop", "ajax security", "winnti", "copper", "lead", "dust", "night dragon",
    "lotus", "naikon", "thrip", "orangeworm", "mofang", "axiom", "group5",
}
ACTOR_WORDS = (
    r"group|gang|team|apt|actor|actors|hackers|hacker|hacking|ransomware|malware|backdoor|"
    r"campaign|operators|threat|crew|implant|cluster|espionage|apt group|state-sponsored"
)
MIN_LEN = 4


@dataclass(frozen=True)
class Match:
    group_id: int
    text: str


@dataclass
class _Entry:
    group_id: int
    alias: str
    pattern: re.Pattern


def _alias_variants(group: Group) -> set[str]:
    names = {group.name, *(a.alias for a in group.aliases)}
    for n in list(names):
        m = re.match(r"^(.*\S)\s+(Group|Team)$", n)
        if m and len(m.group(1)) >= MIN_LEN:
            names.add(m.group(1))
    return {n for n in names if len(n) >= MIN_LEN}


def _compile(alias: str) -> re.Pattern:
    esc = re.escape(alias)
    if alias.lower() in AMBIGUOUS:
        return re.compile(
            rf"(?:\b(?i:{ACTOR_WORDS})\s+(?i:dubbed\s+|called\s+|known as\s+)?{esc}\b"
            rf"|\b{esc}\s+(?i:{ACTOR_WORDS})\b)"
        )
    # Distinctive alias: case-insensitive, tolerate '-' vs ' ' differences ("UAC 0056").
    flexible = re.sub(r"\\[ \-]", r"[\\s\\-]?", esc)
    return re.compile(rf"(?<![\w$]){flexible}(?![\w$])", re.IGNORECASE)


class GroupMatcher:
    def __init__(self, groups: list[Group]):
        self.entries: list[_Entry] = []
        seen: dict[str, int] = {}
        for g in groups:
            for alias in _alias_variants(g):
                key = alias.lower()
                # Same alias claimed by two groups (vendor naming collisions): drop it entirely.
                if key in seen and seen[key] != g.id:
                    seen[key] = -1
                    continue
                seen[key] = g.id
        for g in groups:
            for alias in _alias_variants(g):
                if seen.get(alias.lower()) == g.id:
                    self.entries.append(_Entry(g.id, alias, _compile(alias)))
        # Longest aliases first so "Sandworm Team" wins over "Sandworm" for matched_text.
        self.entries.sort(key=lambda e: -len(e.alias))
        self._by_lower = {e.alias.lower(): e.group_id for e in self.entries}

    @classmethod
    def from_db(cls, db: Session) -> "GroupMatcher":
        groups = db.scalars(select(Group).options(selectinload(Group.aliases))).all()
        return cls(list(groups))

    def match(self, text: str) -> list[Match]:
        found: dict[int, str] = {}
        for e in self.entries:
            if e.group_id in found:
                continue
            m = e.pattern.search(text)
            if m:
                found[e.group_id] = e.alias
        return [Match(gid, alias) for gid, alias in found.items()]

    def lookup(self, name: str) -> int | None:
        """Exact (case-insensitive) alias lookup, used for structured fields like OTX 'adversary'."""
        return self._by_lower.get(name.strip().lower())
