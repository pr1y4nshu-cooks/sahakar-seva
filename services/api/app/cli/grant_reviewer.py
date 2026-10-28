"""Grant or revoke dispute-reviewer rights. Server-side only; there is deliberately no API for this.

    python -m app.cli.grant_reviewer --email reviewer@demo.sahakar.test [--note "pilot reviewer"]
    python -m app.cli.grant_reviewer --email reviewer@demo.sahakar.test --revoke

The user must have signed in at least once (so their account row exists).
"""

import argparse
import sys

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.marketplace import PlatformReviewer
from app.models.user import User


def grant(db, user, note: str | None = None) -> bool:
    """Grant dispute-reviewer rights inside ``db`` (commits). Returns False if already granted.

    Same effect as ``python -m app.cli.grant_reviewer``; shared with the demo seeder so there is one code path.
    """
    if db.get(PlatformReviewer, user.id):
        return False
    db.add(PlatformReviewer(user_id=user.id, note=note))
    db.commit()
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True)
    parser.add_argument("--note", default=None)
    parser.add_argument("--revoke", action="store_true")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == args.email.strip().lower()))
        if user is None:
            print(f"No user with email {args.email!r}. Ask them to sign in once first.", file=sys.stderr)
            return 1
        existing = db.get(PlatformReviewer, user.id)
        if args.revoke:
            if existing:
                db.delete(existing)
                db.commit()
            print(f"Reviewer rights revoked for {user.email}.")
            return 0
        if not grant(db, user, args.note):
            print(f"{user.email} is already a reviewer.")
            return 0
        print(f"Granted dispute-reviewer rights to {user.email}.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
