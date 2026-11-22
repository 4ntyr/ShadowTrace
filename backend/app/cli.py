"""Admin CLI.

  python -m app.cli init                 create tables, seed MITRE snapshot + curation
  python -m app.cli run <job>            run one job: rss | otx | gdelt | acled | correlate | mitre
  python -m app.cli create-user <email> <display name>   create an account (prompts for password)
  python -m app.cli reset-password <email>               set a new password, signs out all sessions
  python -m app.cli make-admin <email>                   flag a user as admin

Passwords can be piped instead of typed: echo "$PW" | python -m app.cli create-user ... --password-stdin
"""

import argparse
import getpass
import json
import logging
import sys
from datetime import datetime, timezone

from sqlalchemy import select

from .db import SessionLocal, init_db
from .ingest.runner import JOBS, bootstrap
from .models import User
from .security import hash_password


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        pw = sys.stdin.readline().rstrip("\n")
    else:
        pw = getpass.getpass("Password: ")
        if pw != getpass.getpass("Repeat password: "):
            raise SystemExit("passwords do not match")
    if not 10 <= len(pw) <= 128:
        raise SystemExit("password must be 10-128 characters")
    return pw


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    p = argparse.ArgumentParser(prog="shadowtrace")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    r = sub.add_parser("run")
    r.add_argument("job", choices=sorted(JOBS))
    a = sub.add_parser("make-admin")
    a.add_argument("email")
    c = sub.add_parser("create-user")
    c.add_argument("email")
    c.add_argument("display_name")
    c.add_argument("--admin", action="store_true")
    c.add_argument("--password-stdin", action="store_true")
    rp = sub.add_parser("reset-password")
    rp.add_argument("email")
    rp.add_argument("--password-stdin", action="store_true")
    args = p.parse_args()

    init_db()
    db = SessionLocal()
    try:
        if args.cmd == "init":
            print(json.dumps(bootstrap(db), indent=2, default=str))
        elif args.cmd == "run":
            print(JOBS[args.job](db))
        elif args.cmd == "create-user":
            email = args.email.strip().lower()
            if db.scalar(select(User).where(User.email == email)):
                raise SystemExit(f"user {email} already exists")
            pw = _read_password(args.password_stdin)
            db.add(User(email=email, display_name=args.display_name, password_hash=hash_password(pw), is_admin=args.admin))
            db.commit()
            print(f"created {email}")
        elif args.cmd == "reset-password":
            u = db.scalar(select(User).where(User.email == args.email.strip().lower()))
            if not u:
                raise SystemExit(f"no user {args.email}")
            u.password_hash = hash_password(_read_password(args.password_stdin))
            u.password_changed_at = datetime.now(timezone.utc).replace(microsecond=0)
            db.commit()
            print(f"password reset for {u.email}; existing sessions are signed out")
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
