"""Background worker: schedules all connectors. Run as a single process (one per deployment)."""

import logging
import signal
import sys

from apscheduler.schedulers.blocking import BlockingScheduler

from .db import SessionLocal, init_db
from .ingest.runner import JOBS, bootstrap

log = logging.getLogger("shadowtrace.worker")

SCHEDULE = {  # job -> minutes between runs
    "rss": 30,
    "otx": 60,
    "gdelt": 15,
    "acled": 360,
    "correlate": 30,
    "mitre": 7 * 24 * 60,
}


def _run(name: str) -> None:
    db = SessionLocal()
    try:
        n = JOBS[name](db)
        log.info("job %s finished: %s", name, n)
    except Exception:  # noqa: BLE001
        log.exception("job %s crashed", name)
    finally:
        db.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_db()
    db = SessionLocal()
    try:
        log.info("bootstrap: %s", bootstrap(db))
    finally:
        db.close()

    sched = BlockingScheduler(timezone="UTC")
    for name, minutes in SCHEDULE.items():
        sched.add_job(_run, "interval", minutes=minutes, args=[name], id=name,
                      max_instances=1, coalesce=True, misfire_grace_time=600)
    # Kick off the live feeds immediately, then correlate.
    for name in ("gdelt", "rss", "otx", "acled", "correlate"):
        _run(name)

    def stop(*_):
        sched.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop)
    sched.start()


if __name__ == "__main__":
    main()
