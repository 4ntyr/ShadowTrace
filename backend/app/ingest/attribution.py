"""Conservative extraction of state attribution from MITRE ATT&CK group descriptions.

MITRE ATT&CK has no structured "attributed country" field, but most descriptions open with
phrases like "a suspected Chinese cyber espionage group" or "attributed to Russia's GRU". Only
the first sentences are inspected, and only phrasings that express origin (not targeting) count.
Extracted links are stored with confidence "low" and a note so the UI can flag them; curated
attributions always take precedence.
"""

import re

NATIONS = {
    "CN": r"Chin(?:a|ese)|PRC",
    "RU": r"Russia(?:n)?(?!-speaking)",
    "IR": r"Iran(?:ian)?",
    "KP": r"North Korea(?:n)?|DPRK",
    "VN": r"Vietnam(?:ese)?",
    "PK": r"Pakistan(?:i)?",
    "IN": r"India(?:n)?",
    "LB": r"Leban(?:on|ese)",
    "BY": r"Belarus(?:ian)?",
    "TR": r"Turk(?:ey|ish|iye)",
    "KR": r"South Korea(?:n)?",
    "AE": r"United Arab Emirates|UAE",
    "PS": r"Gaza|Palestinian",
    "ES": r"Spanish",
    "KZ": r"Kazakh(?:stan)?",
}
BEFORE = r"(?:suspected|likely|probable|possibly|attributed to(?: the)?(?: (?:actors|operators)(?: (?:operating|based))?(?: (?:out of|in|from))?)?|operat\w* (?:out of|from|in)|based in|located in|from|is an?|nexus|sponsored by(?: the)?|linked to(?: the)?|on behalf of(?: the)?)\s+(?:the\s+)?"
AFTER = r"(?:-based|-nexus|-linked|-sponsored|-aligned|\s+state|\s+government|\s+threat|\s+cyber|\s+espionage|\s+actor|\s+group|\s+APT|\s+military|\s+intelligence|\s+hack|'s|’s)"

_PATTERNS = {
    code: re.compile(rf"(?:{BEFORE}(?:{n})\b(?!-speaking)|\b(?:{n})(?!-speaking){AFTER})") for code, n in NATIONS.items()
}


def extract_countries(description: str) -> list[str]:
    head = re.split(r"(?<=[.!?])\s+", description or "")
    text = head[0][:450]  # first sentence: later ones often mention *other* groups
    found = []
    for code, pat in _PATTERNS.items():
        for m in pat.finditer(text):
            window = text[max(0, m.start() - 60) : m.start()].lower()
            if "target" in window or "against" in window or "victim" in window:
                continue
            found.append((m.start(), code))
            break
    return [c for _, c in sorted(found)]


def is_criminal(description: str) -> bool:
    head = (description or "")[:400].lower()
    return bool(re.search(r"financially[- ]motivated|cybercriminal|criminal group|ransomware[- ]as[- ]a[- ]service|extortion group", head))
