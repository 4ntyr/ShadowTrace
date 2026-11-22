from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ST_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://shadowtrace:shadowtrace@localhost:5432/shadowtrace"

    # Auth
    secret_key: str = "change-me-in-production"
    session_hours: int = 24 * 7
    cookie_secure: bool = False  # set true behind HTTPS
    allow_registration: bool = True

    # MITRE ATT&CK
    mitre_url: str = (
        "https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json"
    )

    # AlienVault OTX (free key from https://otx.alienvault.com)
    otx_api_key: str | None = None
    otx_base_url: str = "https://otx.alienvault.com"

    # ACLED (free registration at https://acleddata.com). OAuth password grant.
    acled_username: str | None = None
    acled_password: str | None = None
    acled_base_url: str = "https://acleddata.com"
    acled_lookback_days: int = 60

    # GDELT 2.0 events (no key)
    gdelt_enabled: bool = True
    gdelt_lastupdate_url: str = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"
    gdelt_backfill_files: int = 96  # 15-min files, 96 = last 24h on first run
    gdelt_min_sources: int = 1

    # RSS
    rss_enabled: bool = True

    # Correlation
    correlation_window_days: int = 3

    http_user_agent: str = "ShadowTrace/1.0 (+threat-intel research tracker)"


@lru_cache
def get_settings() -> Settings:
    return Settings()
