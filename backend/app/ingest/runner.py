"""Entry points that combine connectors; used by the worker and the CLI."""

import logging

from sqlalchemy.orm import Session

from .. import correlation
from . import acled, curation, gdelt, mitre, otx, rss
from .common import run_tracked

log = logging.getLogger(__name__)


def bootstrap(db: Session, refresh_mitre: bool = False) -> dict:
    """Seed reference data, MITRE ATT&CK and curation. Safe to run repeatedly."""
    curation.seed_countries(db)

    def mitre_job(_row) -> int:
        snap = None
        if refresh_mitre:
            snap = mitre.download_snapshot()
            mitre.write_snapshot(snap)
        snap = snap or mitre.load_snapshot()
        return mitre.import_snapshot(db, snap)["groups"]

    run_tracked(db, "mitre", "MITRE ATT&CK Enterprise", "mitre", mitre_job)
    g = curation.apply_group_curation(db)
    c = curation.apply_conflict_curation(db)
    return {"groups": g, "conflicts": c}


def refresh_mitre(db: Session) -> dict:
    return bootstrap(db, refresh_mitre=True)


def run_correlation(db: Session) -> int:
    return run_tracked(db, "correlation", "Hybrid correlation engine", "correlation",
                       lambda _row: correlation.correlate_all(db))


JOBS = {
    "rss": rss.run,
    "otx": otx.run,
    "gdelt": gdelt.run,
    "acled": acled.run,
    "correlate": run_correlation,
    "mitre": refresh_mitre,
}
