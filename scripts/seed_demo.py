#!/usr/bin/env python3
"""Seed / inspect the synthetic judge-demo dataset in the LOCAL Docker development database.

    python3 scripts/seed_demo.py --dry-run | --apply | --status | --verify

It runs `python -m app.cli.seed_demo` inside the API container, whose DATABASE_URL (db:5432/sahakar_seva) is the
local Docker PostgreSQL, so the root .env's historical remote Supabase settings can never be used. The seeder
itself refuses non-development, remote, Supabase or test databases. With --verify this wrapper additionally
downloads the public showcase receipts and checks them with scripts/verify_receipt.py WITHOUT the database.
"""
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "http://127.0.0.1:8000/api/v1"


def _toolchain() -> tuple[str, dict]:
    """A Python that has asn1crypto, and an OpenSSL that can verify RFC 3161 tokens (macOS /usr/bin/openssl cannot)."""
    py = next((p for p in (str(ROOT / "services" / "api" / ".venv" / "bin" / "python"), sys.executable)
               if Path(p).exists() and subprocess.run([p, "-c", "import asn1crypto"], capture_output=True).returncode == 0), sys.executable)
    env = dict(os.environ)
    for cand in (env.get("OPENSSL_BIN"), shutil.which("openssl"), "/opt/homebrew/bin/openssl", "/usr/local/opt/openssl@3/bin/openssl", "/opt/homebrew/opt/openssl@3/bin/openssl"):
        if cand and Path(cand).exists():
            r = subprocess.run([cand, "ts", "-help"], capture_output=True, text=True)
            if "-attime" in r.stdout + r.stderr:
                env["OPENSSL_BIN"] = cand
                break
    return py, env


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] not in ("--dry-run", "--apply", "--status", "--verify", "--json", "--allow-database"):
        print(__doc__)
        return 2
    run = subprocess.run(["docker", "compose", "exec", "-T", "api", "python", "-m", "app.cli.seed_demo", *args], cwd=ROOT)
    if run.returncode != 0 or "--verify" not in args:
        return run.returncode
    print("\nOffline verification of public showcase receipts (no database or API internals; only the exported JSON):")
    try:
        guide = json.load(urllib.request.urlopen(f"{API}/demo/guide", timeout=10))
    except Exception as exc:  # noqa: BLE001
        print(f"  could not read /demo/guide: {exc}")
        return 1
    root = ROOT / "services" / "api" / "trust" / "tsa" / "digicert-trusted-root-g4.pem"
    out = Path("/tmp/sahakar-demo-receipts")
    out.mkdir(exist_ok=True)
    worst = 0
    py, env = _toolchain()
    print(f"  verifier python: {py}; openssl: {env.get('OPENSSL_BIN', 'NOT FOUND (token checks will be reported as unavailable)')}")
    for item in guide["showcase"]:
        path = out / f"{item['key']}.json"
        path.write_bytes(urllib.request.urlopen(f"{API}/demo/showcase/{item['key']}/receipt", timeout=20).read())
        p = subprocess.run([py, str(ROOT / "scripts" / "verify_receipt.py"), str(path), "--json", "--tsa-ca", str(root)], capture_output=True, text=True, env=env)
        res = json.loads(p.stdout) if p.stdout.strip() else {"result": "NO OUTPUT", "events_total": 0, "events_externally_timestamped": 0}
        print(f"  {item['key']:24s} {res['result']:38s} {res['events_externally_timestamped']}/{res['events_total']} events externally timestamped")
        worst = max(worst, 1 if res["result"] == "VERIFICATION FAILED" else 0)
    print(f"  receipts saved in {out}")
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
