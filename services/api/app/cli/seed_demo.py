"""Synthetic judge-demo data. Local development database only.

    python -m app.cli.seed_demo --dry-run      # show the plan; performs NO writes
    python -m app.cli.seed_demo --apply        # create/complete the dataset (idempotent)
    python -m app.cli.seed_demo --status       # counts and availability
    python -m app.cli.seed_demo --verify       # relationships, state machine, money, ledger, receipts

Refuses unless APP_ENV=development and DATABASE_URL is a local, non-test, non-Supabase PostgreSQL whose name is
the intended development database and whose migrations are at head. There is deliberately no reset/delete.
From the repository root use:  python3 scripts/seed_demo.py <mode>   (runs this inside the API container)
"""

import argparse
import json
import sys

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.demo import seed as seeder
from app.demo.verify import verify


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    for mode in ("dry-run", "apply", "status", "verify"):
        g.add_argument(f"--{mode}", action="store_true")
    ap.add_argument("--allow-database", help="override the expected development database name (still must be local and not a test DB)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    settings = get_settings()
    try:
        safety = seeder.check_safety(settings.database_url, settings.app_env, args.allow_database)
    except seeder.SeedSafetyError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 3
    print(f"target: {safety.host}:{safety.port or 5432}/{safety.database}  APP_ENV={safety.app_env}  (local development database)")
    with SessionLocal() as db:
        try:
            seeder.assert_runtime_target(db, safety)
        except seeder.SeedSafetyError as exc:
            if args.dry_run and "migration" in str(exc):
                print(f"note: {exc} (dry-run only; nothing is written)")
            else:
                print(f"REFUSED: {exc}", file=sys.stderr)
                return 3
        if args.dry_run:
            db.rollback()
            db.execute(__import__("sqlalchemy").text("SET TRANSACTION READ ONLY"))
            print("DRY RUN — no database writes. Plan for dataset 'judge-demo' v%d:" % seeder.ds.DATASET_VERSION)
            for line in seeder.plan(db):
                print("  " + line)
            print(f"  organization-scoped example fee policies: {[o.policy_id for o in seeder.ds.ORGS if o.policy]}")
            print("  every booking is created through the real services; quotes, ledger and events are genuine; no external timestamps are fabricated")
            return 0
        if args.apply:
            before = seeder.non_demo_counts(db)
            ctx = seeder.run_seed(db)
            after = seeder.non_demo_counts(db)
            print("created:", dict(ctx.created) or "nothing new")
            print("already present:", dict(ctx.existing) or "none")
            if ctx.skipped:
                print("skipped:", *ctx.skipped, sep="\n  ")
            print("non-demo rows before/after (must be identical):", "IDENTICAL" if before == after else f"CHANGED {before} -> {after}")
            return 0 if before == after else 4
        if args.status:
            st = seeder.status(db)
            print(json.dumps(st, indent=2, default=str) if args.json else "\n".join(f"{k}: {v}" for k, v in st.items()))
            return 0
        report = verify(db)
        for name, ok, detail in report.checks:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")
        print(f"{sum(1 for c in report.checks if c[1])}/{len(report.checks)} checks passed")
        return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
