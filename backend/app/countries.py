"""Country reference data and name/code normalisation."""

import json
import re
from functools import lru_cache

from .config import DATA_DIR

# GDELT geocodes with FIPS 10-4 country codes, not ISO 3166. This covers every country
# GDELT emits regularly; unknown codes are dropped by the GDELT connector.
FIPS_TO_ISO2 = {
    "AF": "AF", "AL": "AL", "AG": "DZ", "AN": "AD", "AO": "AO", "AC": "AG", "AR": "AR",
    "AM": "AM", "AS": "AU", "AU": "AT", "AJ": "AZ", "BF": "BS", "BA": "BH", "BG": "BD",
    "BB": "BB", "BO": "BY", "BE": "BE", "BH": "BZ", "BN": "BJ", "BT": "BT", "BL": "BO",
    "BK": "BA", "BC": "BW", "BR": "BR", "BX": "BN", "BU": "BG", "UV": "BF", "BM": "MM",
    "BY": "BI", "CB": "KH", "CM": "CM", "CA": "CA", "CV": "CV", "CT": "CF", "CD": "TD",
    "CI": "CL", "CH": "CN", "CO": "CO", "CN": "KM", "CG": "CD", "CF": "CG", "CS": "CR",
    "IV": "CI", "HR": "HR", "CU": "CU", "CY": "CY", "EZ": "CZ", "DA": "DK", "DJ": "DJ",
    "DO": "DM", "DR": "DO", "EC": "EC", "EG": "EG", "ES": "SV", "EK": "GQ", "ER": "ER",
    "EN": "EE", "WZ": "SZ", "ET": "ET", "FJ": "FJ", "FI": "FI", "FR": "FR", "GB": "GA",
    "GA": "GM", "GG": "GE", "GM": "DE", "GH": "GH", "GR": "GR", "GJ": "GD", "GT": "GT",
    "GV": "GN", "PU": "GW", "GY": "GY", "HA": "HT", "HO": "HN", "HK": "HK", "HU": "HU",
    "IC": "IS", "IN": "IN", "ID": "ID", "IR": "IR", "IZ": "IQ", "EI": "IE", "IS": "IL",
    "IT": "IT", "JM": "JM", "JA": "JP", "JO": "JO", "KZ": "KZ", "KE": "KE", "KR": "KI",
    "KN": "KP", "KS": "KR", "KV": "XK", "KU": "KW", "KG": "KG", "LA": "LA", "LG": "LV",
    "LE": "LB", "LT": "LS", "LI": "LR", "LY": "LY", "LS": "LI", "LH": "LT", "LU": "LU",
    "MA": "MG", "MI": "MW", "MY": "MY", "MV": "MV", "ML": "ML", "MT": "MT", "RM": "MH",
    "MR": "MR", "MP": "MU", "MX": "MX", "FM": "FM", "MD": "MD", "MN": "MC", "MG": "MN",
    "MJ": "ME", "MO": "MA", "MZ": "MZ", "WA": "NA", "NP": "NP", "NL": "NL", "NZ": "NZ",
    "NU": "NI", "NG": "NE", "NI": "NG", "MK": "MK", "NO": "NO", "MU": "OM", "PK": "PK",
    "PS": "PW", "PM": "PA", "PP": "PG", "PA": "PY", "PE": "PE", "RP": "PH", "PL": "PL",
    "PO": "PT", "QA": "QA", "RO": "RO", "RS": "RU", "RW": "RW", "SC": "KN", "ST": "LC",
    "VC": "VC", "WS": "WS", "SM": "SM", "TP": "ST", "SA": "SA", "SG": "SN", "RI": "RS",
    "SE": "SC", "SL": "SL", "SN": "SG", "LO": "SK", "SI": "SI", "BP": "SB", "SO": "SO",
    "SF": "ZA", "OD": "SS", "SP": "ES", "CE": "LK", "SU": "SD", "NS": "SR", "SW": "SE",
    "SZ": "CH", "SY": "SY", "TW": "TW", "TI": "TJ", "TZ": "TZ", "TH": "TH", "TT": "TL",
    "TO": "TG", "TN": "TO", "TD": "TT", "TS": "TN", "TU": "TR", "TX": "TM", "UG": "UG",
    "UP": "UA", "AE": "AE", "UK": "GB", "US": "US", "UY": "UY", "UZ": "UZ", "NH": "VU",
    "VE": "VE", "VM": "VN", "YM": "YE", "ZA": "ZM", "ZI": "ZW", "GZ": "PS", "WE": "PS",
    "WI": "EH", "CY": "CY", "RQ": "PR", "GL": "GL",
}


@lru_cache
def load_countries() -> list[dict]:
    with open(DATA_DIR / "countries.json", encoding="utf-8") as f:
        return json.load(f)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


@lru_cache
def _name_index() -> dict[str, str]:
    idx: dict[str, str] = {}
    for c in load_countries():
        idx[_norm(c["name"])] = c["code"]
        for alt in c["alt_names"]:
            idx.setdefault(_norm(alt), c["code"])
        idx.setdefault(_norm(c["iso3"] or ""), c["code"])
    idx.pop("", None)
    return idx


def iso2_from_name(name: str | None) -> str | None:
    """Map a free-text country name ("Russian Federation", "Ukraine") to ISO2."""
    if not name:
        return None
    s = name.strip()
    if len(s) == 2 and s.upper() in valid_codes():
        return s.upper()
    return _name_index().get(_norm(s))


@lru_cache
def valid_codes() -> frozenset[str]:
    return frozenset(c["code"] for c in load_countries())


def country_name(code: str) -> str:
    for c in load_countries():
        if c["code"] == code:
            return c["name"]
    return code


def iso2_from_fips(fips: str | None) -> str | None:
    if not fips:
        return None
    return FIPS_TO_ISO2.get(fips.upper())
