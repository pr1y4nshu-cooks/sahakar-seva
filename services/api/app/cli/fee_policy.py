"""Manage fee policies. Server-side only; there is deliberately no API that writes pricing.

    python -m app.cli.fee_policy list
    python -m app.cli.fee_policy show --policy-id P [--version N]
    python -m app.cli.fee_policy create --policy-id P --file policy.json [--organization-id UUID] [--note TEXT]
    python -m app.cli.fee_policy activate --policy-id P --version N
    python -m app.cli.fee_policy bootstrap-example      # local dev: activate the illustrative example if none is active

Creating writes an immutable draft version. Activating retires the previous active policy of the same scope,
records a 'fee_policy_activated' event in the hash chain, and affects ONLY quotes created afterwards.
Example definitions: services/api/fee_policies/examples/*.json (illustrative, not official pricing).
"""

import argparse
import json
import sys
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.trust import FeePolicy
from app.services import fee_policy_service as fps


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    show = sub.add_parser("show")
    show.add_argument("--policy-id", required=True)
    show.add_argument("--version", type=int)
    create = sub.add_parser("create")
    create.add_argument("--policy-id", required=True)
    create.add_argument("--file", required=True)
    create.add_argument("--organization-id", type=UUID)
    create.add_argument("--note")
    act = sub.add_parser("activate")
    act.add_argument("--policy-id", required=True)
    act.add_argument("--version", type=int, required=True)
    sub.add_parser("bootstrap-example")
    args = ap.parse_args(argv)

    with SessionLocal() as db:
        if args.cmd == "list":
            for fp in db.scalars(select(FeePolicy).order_by(FeePolicy.scope, FeePolicy.policy_id, FeePolicy.version)):
                org = f" org={fp.organization_id}" if fp.organization_id else ""
                print(f"{fp.policy_id} v{fp.version} [{fp.status}] {fp.scope}{org} {fp.pricing_model} "
                      f"ceiling={fp.max_total_charge_bps}bps example={fp.is_example} hash={fp.definition_hash[:16]}… — {fp.label}")
            return 0
        if args.cmd == "show":
            q = select(FeePolicy).where(FeePolicy.policy_id == args.policy_id)
            q = q.where(FeePolicy.version == args.version) if args.version else q.order_by(FeePolicy.version.desc())
            fp = db.scalars(q).first()
            if fp is None:
                print("not found", file=sys.stderr)
                return 1
            print(json.dumps(fps.policy_view(fp), indent=2, default=str))
            return 0
        if args.cmd == "create":
            try:
                with open(args.file, encoding="utf-8") as fh:
                    fp = fps.create_version(db, json.load(fh), args.policy_id, organization_id=args.organization_id, note=args.note)
            except (OSError, ValueError, ValidationError) as exc:
                print(f"rejected: {exc}", file=sys.stderr)
                return 1
            db.commit()
            print(f"created draft {fp.policy_id} v{fp.version} ({fp.pricing_model}, hash {fp.definition_hash[:16]}…). Activate it explicitly.")
            return 0
        if args.cmd == "activate":
            fp = db.scalar(select(FeePolicy).where(FeePolicy.policy_id == args.policy_id, FeePolicy.version == args.version))
            if fp is None:
                print("not found", file=sys.stderr)
                return 1
            try:
                fps.activate(db, fp)
            except ValueError as exc:
                print(f"rejected: {exc}", file=sys.stderr)
                return 1
            db.commit()
            print(f"activated {fp.policy_id} v{fp.version}. Existing bookings keep their accepted quotes.")
            return 0
        fp = fps.bootstrap_example(db, get_settings())
        db.commit()
        print(f"activated illustrative example {fp.policy_id} v{fp.version}" if fp else "an active default policy already exists; nothing changed")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
