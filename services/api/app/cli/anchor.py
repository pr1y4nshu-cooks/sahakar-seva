"""Operate the checkpoint / external-timestamp outbox. Server-side only.

    python -m app.cli.anchor --once          # checkpoint new events and submit due checkpoints now
    python -m app.cli.anchor --status        # list checkpoints and their honest status
    python -m app.cli.anchor --retry-failed  # re-queue ANCHOR_FAILED / PROOF_INVALID with a fresh retry budget

No network call happens inside a database transaction (see app/trust/anchoring.py).
"""

import argparse
import json

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.trust import AnchorCheckpoint
from app.trust import anchoring


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--once", action="store_true")
    group.add_argument("--status", action="store_true")
    group.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args(argv)
    settings = get_settings()
    if args.once:
        print(json.dumps(anchoring.run_cycle(SessionLocal, settings), indent=2, default=str))
    elif args.retry_failed:
        with SessionLocal() as db:
            print(f"re-queued {anchoring.retry_failed(db, settings)} checkpoint(s)")
    print(f"TSA configured: {settings.tsa_configured} ({settings.tsa_name or settings.tsa_url or 'none'})")
    with SessionLocal() as db:
        for cp in db.scalars(select(AnchorCheckpoint).order_by(AnchorCheckpoint.checkpoint_index)):
            print(f"#{cp.checkpoint_index} events {cp.first_sequence}-{cp.last_sequence} {cp.digest[:16]}… "
                  f"{cp.anchor_status} attempts={cp.attempt_count} gen_time={cp.tsa_gen_time} {cp.last_error or ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
