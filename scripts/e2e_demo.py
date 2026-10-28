"""Live end-to-end demo against the running local stack (http://localhost:8000).

Uses the local development identity provider (DEV_AUTH_ENABLED=true), real PostgreSQL/PostGIS and the
same endpoints the React app calls. Every run creates new, uniquely tagged @demo.sahakar.test identities;
it never modifies pre-existing rows. Run from the repository root:

    DEV_AUTH_PASSCODE=... python3 scripts/e2e_demo.py

Exit code 0 means every scenario behaved as expected.
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

API = os.environ.get("API", "http://localhost:8000/api/v1")
PASSCODE = os.environ.get("DEV_AUTH_PASSCODE")
TAG = uuid.uuid4().hex[:6]
RESULTS: list[tuple[str, bool, str]] = []

KORAMANGALA = {"locality": "Koramangala", "latitude": 12.9352, "longitude": 77.6245}
HSR = {"locality": "HSR Layout", "latitude": 12.9116, "longitude": 77.6474}
BTM = {"locality": "BTM Layout", "latitude": 12.9166, "longitude": 77.6101}
WHITEFIELD = {"locality": "Whitefield", "latitude": 12.9698, "longitude": 77.7500}


def call(method: str, path: str, token: str | None = None, body: dict | None = None, query: str = "") -> tuple[int, dict]:
    req = urllib.request.Request(f"{API}{path}{query}", method=method, data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, json.loads(raw) if raw else {}


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")


def login(who: str) -> str:
    status, body = call("POST", "/dev-auth/token", body={"email": f"{who}-{TAG}@demo.sahakar.test", "passcode": PASSCODE, "display_name": who.title()})
    assert status == 200, (status, body)
    return body["access_token"]


def at(days: int, hour: int) -> str:
    base = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(days=days)
    return base.replace(hour=hour).isoformat()


def main() -> int:
    if not PASSCODE:
        print("Set DEV_AUTH_PASSCODE (the value from your root .env).", file=sys.stderr)
        return 2
    print(f"Run tag: {TAG}")
    skills = {s["slug"]: s for s in call("GET", "/skills")[1]}
    desk = skills["desk-assembly"]["id"]

    print("\nScenario 1 — worker onboarding")
    worker = login("ravi")
    s, me = call("GET", "/users/me", worker)
    check("protected /users/me with server-verified token", s == 200, me.get("email", ""))
    s, _ = call("POST", "/worker-profiles", worker, {"display_name": f"Ravi Kumar {TAG}", "bio": "Flat-pack furniture, 6 years."})
    check("create worker profile", s == 201)
    s, ws = call("POST", "/worker-profiles/me/skills", worker, {"skill_id": desk})
    check("declare furniture assembly skill (self-declared)", s == 201 and ws["is_self_declared"] is True)
    s, st = call("PUT", "/worker-profiles/me/service-settings", worker, {**KORAMANGALA, "radius_km": 5, "hourly_rate_paise": 35000})
    check("set 5 km service radius around Koramangala (rounded)", s == 200 and st["latitude"] == 12.94, f"stored centre {st.get('latitude')},{st.get('longitude')}")
    s, slot = call("POST", "/worker-profiles/me/availability", worker, {"starts_at": at(2, 10), "ends_at": at(2, 12)})
    check("add a 2-hour availability slot", s == 201)
    _, again = call("GET", "/worker-profiles/me/skills", worker)
    _, slots = call("GET", "/worker-profiles/me/availability", worker)
    check("data persists on re-read (refresh)", len(again) == 1 and any(x["id"] == slot["id"] for x in slots))

    print("\nScenario 2 — direct hire")
    asha = login("asha")
    q = f"?latitude={HSR['latitude']}&longitude={HSR['longitude']}&radius_km=5&skill_id={desk}&starts_at={at(2, 10).replace('+', '%2B')}&ends_at={at(2, 11).replace('+', '%2B')}"
    _, res = call("GET", "/workers/search", asha, query=q)
    mine = [r for r in res["results"] if r["display_name"] == f"Ravi Kumar {TAG}"]
    check("customer in HSR Layout finds the worker (skill + radius + availability)", len(mine) == 1,
          f"{mine[0]['distance_km']} km, '{mine[0]['verification_label']}'" if mine else "")
    check("search result exposes no worker coordinates", mine and "latitude" not in mine[0])
    qw = f"?latitude={WHITEFIELD['latitude']}&longitude={WHITEFIELD['longitude']}&radius_km=25&skill_id={desk}"
    _, far = call("GET", "/workers/search", asha, query=qw)
    check("customer in Whitefield (~14 km) does not see the 5 km-radius worker", not any(r["display_name"] == f"Ravi Kumar {TAG}" for r in far["results"]))
    s, booking = call("POST", "/bookings", asha, {"worker_profile_id": me and mine[0]["worker_profile_id"], "slot_id": slot["id"], "skill_id": desk,
                                                  **HSR, "address_details": "Flat 4B, Example Residency, 27th Main", "customer_notes": "Two study desks"})
    check("customer requests the booking", s == 201 and booking["status"] == "requested", f"price {booking.get('price', {}).get('price_paise')} paise")
    _, wb = call("GET", f"/bookings/{booking['id']}", worker)
    check("worker cannot see exact address before accepting", wb["address_details"] is None)
    s, acc = call("POST", f"/bookings/{booking['id']}/accept", worker)
    check("worker accepts → confirmed and persisted", s == 200 and acc["status"] == "confirmed" and acc["address_details"] is not None)

    print("\nScenario 3 — posted job")
    meena = login("meena")
    s, job = call("POST", "/jobs", meena, {"skill_id": desk, "title": "Assemble a wardrobe", "description": "One 2-door flat-pack wardrobe, tools available.",
                                           **BTM, "address_details": "House 12, 3rd Main, BTM 2nd Stage", "starts_at": at(3, 9),
                                           "duration_minutes": 180, "budget_paise": 150000})
    check("customer posts a furniture assembly job", s == 201 and job["status"] == "open")
    _, nearby = call("GET", "/jobs/nearby", worker)
    seen = [j for j in nearby if j["id"] == job["id"]]
    check("worker finds the job within their radius (no private address)", len(seen) == 1 and seen[0]["address_details"] is None)
    s, app = call("POST", f"/jobs/{job['id']}/applications", worker, {"message": "Available that morning."})
    check("worker applies", s == 201)
    s, dup = call("POST", f"/jobs/{job['id']}/applications", worker, {})
    check("duplicate application rejected", s == 409 and dup["error"]["code"] == "DUPLICATE_APPLICATION")
    s, jb = call("POST", f"/jobs/{job['id']}/applications/{app['id']}/select", meena)
    check("customer selects the worker → booking requested", s == 201 and jb["origin"] == "job" and jb["status"] == "requested")
    s, jbc = call("POST", f"/bookings/{jb['id']}/accept", worker)
    check("worker confirms the job booking", s == 200 and jbc["status"] == "confirmed")

    print("\nScenario 4 — completion and simulated earnings")
    call("POST", f"/bookings/{booking['id']}/start", worker)
    s, done = call("POST", f"/bookings/{booking['id']}/complete", asha)
    st = done.get("settlement") or {}
    check("customer confirms completion → settlement recorded", s == 200 and done["status"] == "completed" and st.get("is_simulated") is True,
          f"{st.get('gross_paise')} = {st.get('fee_paise')} fee + {st.get('payout_paise')} payout")
    check("settlement labelled SIMULATED PAYMENT", st.get("label") == "SIMULATED PAYMENT — NO REAL MONEY TRANSFERRED")
    s, again = call("POST", f"/bookings/{booking['id']}/complete", asha)
    check("repeat completion rejected (no duplicate financial record)", s == 409)
    _, earn = call("GET", "/earnings/mine", worker)
    check("worker earnings reconcile", earn["totals"]["count"] == 1 and earn["totals"]["reconciles"], json.dumps(earn["totals"]))

    print("\nScenario 5 — failures and protections")
    chen = login("chen")
    s, conflict_job = call("POST", "/jobs", chen, {"skill_id": desk, "title": "Assemble a bookshelf", "description": "Bookshelf assembly at the same time.",
                                                   **HSR, "address_details": "Villa 3, Sector 6", "starts_at": at(3, 10),
                                                   "duration_minutes": 60, "budget_paise": 60000})
    _, capp = call("POST", f"/jobs/{conflict_job['id']}/applications", worker, {})
    _, cb = call("POST", f"/jobs/{conflict_job['id']}/applications/{capp['id']}/select", chen)
    s, err = call("POST", f"/bookings/{cb['id']}/accept", worker)
    check("worker cannot accept a conflicting appointment", s == 409 and err["error"]["code"] == "BOOKING_CONFLICT")
    s, _ = call("GET", f"/bookings/{jb['id']}", chen)
    check("unrelated user cannot read another's booking", s == 404)
    s, _ = call("POST", f"/bookings/{jb['id']}/cancel", chen)
    check("unrelated user cannot modify another's booking", s == 404)
    boss = login("boss")
    _, org = call("POST", "/organizations", boss, {"name": f"Green Coop {TAG}", "organization_type": "cooperative"})
    s, ojob = call("POST", "/jobs", boss, {"skill_id": desk, "title": "Office desk assembly", "description": "Five desks for the coop office.",
                                           **KORAMANGALA, "address_details": "Coop office, 1st floor", "starts_at": at(5, 9),
                                           "duration_minutes": 240, "budget_paise": 400000, "organization_id": org["id"]})
    check("organization owner posts a job for their cooperative", s == 201 and ojob["organization_name"] == org["name"])
    s, e = call("POST", "/jobs", chen, {"skill_id": desk, "title": "Hijack attempt", "description": "Posting for someone else's coop.",
                                        **KORAMANGALA, "address_details": "n/a 12345", "starts_at": at(5, 9), "duration_minutes": 60,
                                        "budget_paise": 10000, "organization_id": org["id"]})
    check("non-member cannot post for another organization", s == 403)
    s, _ = call("GET", f"/jobs/{ojob['id']}/applications", chen)
    check("non-member cannot read another organization's applicants", s == 404)
    fee = subprocess.run(
        ["docker", "compose", "exec", "-T", "api", "python", "-c",
         "from app.core.config import Settings\ntry:\n Settings(platform_fee_bps=1600, platform_fee_cap_bps=1500); print('ACCEPTED')\nexcept ValueError: print('REJECTED')"],
        capture_output=True, text=True)
    check("platform fee above the configured cap is refused", "REJECTED" in fee.stdout)
    db = subprocess.run(
        ["docker", "compose", "exec", "-T", "db", "psql", "-U", "sahakar", "-d", "sahakar_seva", "-v", "ON_ERROR_STOP=1", "-c",
         f"BEGIN; UPDATE bookings SET fee_bps=2500 WHERE id='{jb['id']}'; ROLLBACK;"], capture_output=True, text=True)
    # Since 0005 the price guard trigger rejects any price change on a confirmed booking before the CHECK runs;
    # either database-level rejection satisfies this check (the CHECK itself is covered by tests/db).
    check("database rejects a fee above the 20% ceiling",
          db.returncode != 0 and ("ck_bookings_fee_ceiling" in db.stderr or "agreed price of a" in db.stderr))

    print("\nDispute with human review")
    s, d = call("POST", f"/bookings/{jb['id']}/disputes", meena, {"description": "Worker arrived two hours late and left early."})
    check("customer opens a dispute", s == 201 and d["status"] == "disputed")
    s, _ = call("GET", "/disputes/review-queue", meena)
    check("non-reviewer cannot open the review queue", s == 403)
    reviewer = login("reviewer")
    call("GET", "/users/me", reviewer)
    grant = subprocess.run(["docker", "compose", "exec", "-T", "api", "python", "-m", "app.cli.grant_reviewer",
                            "--email", f"reviewer-{TAG}@demo.sahakar.test", "--note", "demo reviewer"], capture_output=True, text=True)
    check("reviewer rights granted via server-side CLI only", grant.returncode == 0, grant.stdout.strip())
    s, r = call("POST", f"/disputes/{d['dispute']['id']}/resolve", reviewer,
                {"outcome": "resolved_for_customer", "reason": "Both parties confirm the late arrival; customer's complaint upheld."})
    check("independent reviewer records decision and reason", s == 200 and r["outcome"] == "resolved_for_customer")
    _, wv = call("GET", "/worker-profiles/me", worker)
    check("no automated sanction on the worker", wv["onboarding_status"] == "draft")

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed (run tag {TAG}).")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
