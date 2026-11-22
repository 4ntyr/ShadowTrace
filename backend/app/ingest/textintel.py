"""Light-weight heuristics to extract countries, sectors and effect type from report text."""

import re
from functools import lru_cache

from ..countries import load_countries

SECTOR_KEYWORDS = {
    "energy": r"power grid|electric|energy|substation|utility|utilities|oil|gas pipeline|nuclear",
    "telecommunications": r"telecom|mobile operator|carrier|isp\b|satellite",
    "government": r"government|ministry|ministries|embassy|embassies|parliament|diplomat",
    "military": r"military|armed forces|defen[cs]e ministry|army|navy|air force",
    "defence industry": r"defen[cs]e contractor|defen[cs]e industr|aerospace",
    "finance": r"\bbank|financial|payment|swift\b",
    "cryptocurrency": r"crypto|blockchain|exchange hack|defi\b|wallet",
    "healthcare": r"hospital|healthcare|health care|pharma|vaccine",
    "water": r"water utilit|water treatment|wastewater",
    "transportation": r"airport|railway|rail operator|logistics|shipping|maritime|port\b",
    "media": r"broadcaster|newspaper|journalist|media outlet|television|\btv\b",
    "elections": r"election|electoral|ballot|campaign staff",
    "industrial control systems": r"\bics\b|\bscada\b|\bplc\b|operational technology|\bot\b network",
    "technology": r"software supply chain|cloud provider|managed service provider|\bmsp\b|it provider",
}

EFFECT_KEYWORDS = [
    ("disruptive", r"wiper|destructive|sabotage|outage|blackout|disrupt|bricked|ransomware attack on"),
    ("ddos", r"\bddos\b|denial[- ]of[- ]service"),
    ("influence", r"hack-and-leak|disinformation|influence operation|propaganda|deepfake|leaked documents"),
    ("espionage", r"espionage|spear-?phishing|backdoor|exfiltrat|surveillance|intelligence gathering|implant"),
]

_SECTOR_RE = {k: re.compile(v, re.I) for k, v in SECTOR_KEYWORDS.items()}
_EFFECT_RE = [(k, re.compile(v, re.I)) for k, v in EFFECT_KEYWORDS]

# Names too ambiguous for country detection in English prose.
_SKIP_NAMES = {"chad", "jersey", "georgia", "guinea", "turkey", "jordan", "niger", "china town", "us", "u.s."}


@lru_cache
def _country_patterns() -> list[tuple[str, re.Pattern]]:
    out = []
    for c in load_countries():
        names = {c["name"], *c["alt_names"]}
        names = {n for n in names if n.lower() not in _SKIP_NAMES and len(n) > 3}
        if not names:
            continue
        alt = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
        out.append((c["code"], re.compile(rf"\b(?:{alt})\b")))
    # Special cases handled with context
    out.append(("GE", re.compile(r"\bGeorgia(?:n)? (?:government|ministry|president|parliament|Tbilisi)|\bTbilisi\b")))
    out.append(("US", re.compile(r"\bU\.S\.(?= )|\bUnited States\b|\bAmerican (?:government|agencies|companies)")))
    out.append(("TR", re.compile(r"\bTürkiye\b|\bTurkiye\b|\bTurkish (?:government|ministry|companies)")))
    out.append(("JO", re.compile(r"\bJordanian\b")))
    return out


def detect_countries(text: str) -> list[str]:
    found = []
    for code, pat in _country_patterns():
        if code not in found and pat.search(text):
            found.append(code)
    return found


def detect_sectors(text: str) -> list[str]:
    return [k for k, rx in _SECTOR_RE.items() if rx.search(text)]


def detect_effect(text: str) -> str | None:
    for k, rx in _EFFECT_RE:
        if rx.search(text):
            return k
    return None
