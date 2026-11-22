"""Admin CLI.

  python -m app.cli init                 create tables, seed MITRE snapshot + curation
  python -m app.cli run <job>            run one job: rss | otx | gdelt | acled | correlate | mitre
  python -m app.cli make-admin <email>   grant admin rights
"""

import argparse
import json
import logging

from sqlalchemy import select

from .db import SessionLocal, init_db
from .ingest.runner import JOBS, bootstrap
from .models import User


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    p = argparse.ArgumentParser(prog="shadowtrace")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    r = sub.add_parser("run")
    r.add_argument("job", choices=sorted(JOBS))
    a = sub.add_parser("make-admin")
    a.add_argument("email")
    args = p.parse_args()

    init_db()
    db = SessionLocal()
    try:
        if args.cmd == "init":
            print(json.dumps(bootstrap(db), indent=2, default=str))
        elif args.cmd == "run":
            print(JOBS[args.job](db))
        elif args.cmd == "make-admin":
            u = db.scalar(select(User).where(User.email == args.email.lower()))
            if not u:
                raise SystemExit(f"no user {args.email}")
            u.is_admin = True
            db.commit()
            print(f"{u.email} is now admin")
    finally:
        db.close()


if __name__ == "__main__":
    main()
