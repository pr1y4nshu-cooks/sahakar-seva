"""Recompute and check the whole financial event chain, checkpoints and ledger. Server-side only.

    python -m app.cli.verify_ledger [--json]

Exit 0 when internally consistent, 1 otherwise. Internal consistency is not independent proof; see
scripts/verify_receipt.py and the RFC 3161 checkpoint tokens for that.
"""

import argparse
import json

from app.db.session import SessionLocal
from app.trust.integrity import verify_database


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    with SessionLocal() as db:
        report = verify_database(db)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{'OK' if report['ok'] else 'PROBLEMS FOUND'}: {report['events_checked']} events, "
              f"{report['checkpoints_checked']} checkpoints, {report['ledger_transactions_checked']} ledger transactions")
        for p in report["problems"]:
            print(f"  - {p['code']}: {p['detail']} {({k: v for k, v in p.items() if k not in ('code', 'detail')})}")
        print(report["scope_note"])
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
