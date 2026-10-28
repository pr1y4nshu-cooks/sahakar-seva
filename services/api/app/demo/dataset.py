"""Static specification of the demo dataset. No amounts of money are typed for bookings other than the service
price (hourly rate × slot length, or a job budget); customer totals, fees and payouts come from the active
fee policies at seed time.

All people, bios, business names and addresses are invented. Localities and coordinates are the project's
curated neighbourhood centroids (app/core/localities.py); nothing here is anyone's real address.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DATASET = "judge-demo"
DATASET_VERSION = 1
EMAIL_DOMAIN = "demo.sahakar.test"
SYNTHETIC_NOTE = "Synthetic demonstration record created by the demo seeder. Not a real person, business or transaction."
SYNTHETIC_ADDRESS = "{unit}, Sample Apartments (synthetic demo address), {locality}"
DEFAULT_SEARCH_LOCALITY = "Koramangala"
SERVICE_SLUGS = ("basic-home-cleaning", "kitchen-cleaning", "garden-maintenance", "plant-care", "desk-assembly", "shelf-assembly")


def email(local: str) -> str:
    return f"{local}@{EMAIL_DOMAIN}"


@dataclass(frozen=True)
class Persona:
    local: str
    name: str
    role: str  # description for the runbook


@dataclass(frozen=True)
class SlotSpec:
    label: str
    day: int      # days from today (IST); negative = past
    hh: int       # IST hour
    mm: int
    hours: float


@dataclass(frozen=True)
class WorkerSpec:
    local: str
    name: str
    skills: tuple[str, ...]
    locality: str
    radius_km: int
    rate_rupees: int
    pattern: str
    bio: str
    restricted: bool = False


PATTERNS: dict[str, tuple[tuple[int, int, int, float], ...]] = {   # (day, IST hour, minute, hours)
    "mornings": ((1, 9, 30, 2), (2, 10, 0, 2), (3, 10, 0, 3), (5, 9, 0, 3)),
    "afternoons": ((1, 14, 0, 3), (2, 14, 0, 3), (4, 13, 0, 4)),
    "evenings": ((1, 17, 0, 2), (3, 17, 30, 2), (4, 18, 0, 2)),
    "fullday": ((2, 9, 0, 8), (4, 9, 0, 8)),
    "mixed": ((1, 10, 0, 2), (2, 15, 0, 2), (3, 10, 0, 2), (6, 11, 0, 4)),
    "weekend": ((3, 9, 0, 4), (4, 9, 0, 4), (5, 9, 0, 4)),
}

PERSONAS: tuple[Persona, ...] = (
    Persona("asha", "Asha Menon", "Customer. Headline completed ₹500-service booking, repeat booking, open job."),
    Persona("karthik", "Karthik Rao", "Customer. Posted job, completed kitchen-clean booking, resolved dispute with ledger reversal."),
    Persona("deepa", "Deepa Nair", "Customer. In-progress garden booking, open job."),
    Persona("imran", "Imran Sheikh", "Customer and cooperative admin. Confirmed shelf booking."),
    Persona("sunita", "Sunita Patil", "Customer and cooperative member. Pending desk-assembly request."),
    Persona("vikram", "Vikram Shetty", "Owner of BrightDesk Co-working (Demo): repeated maintenance demand, fixed-fee terms."),
    Persona("nandini", "Nandini Iyer", "Customer. Cancelled booking, open job."),
    Persona("arjun", "Arjun Gowda", "Owner of Lakeside Café & Bakery (Demo). Declined booking, cancelled job."),
    Persona("meena", "Meena Krishnan", "Owner of Sahyog Residents Cooperative (Demo): hybrid fee with promotion."),
    Persona("reviewer", "Demo Reviewer", "Platform dispute reviewer (rights granted by the server-side CLI path). Never a party to a booking."),
)

_B = "Demo profile — "
WORKERS: tuple[WorkerSpec, ...] = (
    # cleaning
    WorkerSpec("lakshmi", "Lakshmi Devi", ("basic-home-cleaning", "kitchen-cleaning"), "Koramangala", 10, 220, "mornings", _B + "7 years of apartment and kitchen deep cleaning. Brings own supplies."),
    WorkerSpec("fatima", "Fatima Begum", ("basic-home-cleaning",), "HSR Layout", 10, 200, "afternoons", _B + "Regular home cleaning for families and small offices."),
    WorkerSpec("sunil", "Sunil Kumar", ("kitchen-cleaning",), "BTM Layout", 5, 260, "mixed", _B + "Chimney, hob and kitchen degreasing specialist."),
    WorkerSpec("geeta", "Geeta Sharma", ("basic-home-cleaning", "kitchen-cleaning"), "Jayanagar", 10, 240, "evenings", _B + "Move-in and move-out cleaning. Works in a pair on request."),
    WorkerSpec("rohan", "Rohan D'Souza", ("basic-home-cleaning", "kitchen-cleaning"), "Indiranagar", 10, 300, "weekend", _B + "Studio and apartment cleaning, weekends preferred."),
    WorkerSpec("mary", "Mary Joseph", ("kitchen-cleaning",), "Bellandur", 15, 280, "fullday", _B + "Commercial kitchen and café cleaning after closing hours."),
    # gardening
    WorkerSpec("manjunath", "Manjunath Gowda", ("garden-maintenance", "plant-care"), "Jayanagar", 10, 250, "mornings", _B + "Lawn, hedge and terrace garden care."),
    WorkerSpec("shanti", "Shanti Bai", ("plant-care",), "Koramangala", 5, 210, "afternoons", _B + "Balcony plants, repotting and watering schedules."),
    WorkerSpec("prakash", "Prakash Reddy", ("garden-maintenance",), "BTM Layout", 10, 320, "mixed", _B + "Society courtyards and larger garden beds."),
    WorkerSpec("zainab", "Zainab Khan", ("garden-maintenance", "plant-care"), "HSR Layout", 10, 280, "evenings", _B + "Organic composting and seasonal planting."),
    WorkerSpec("gopal", "Gopal Naik", ("garden-maintenance",), "Bellandur", 15, 240, "weekend", _B + "Weekly garden upkeep for apartment complexes."),
    WorkerSpec("anita", "Anita Rao", ("plant-care",), "Indiranagar", 10, 230, "fullday", _B + "Indoor plants, herb gardens and planters."),
    # furniture assembly
    WorkerSpec("ravi", "Ravi Kumar", ("desk-assembly", "shelf-assembly"), "Koramangala", 10, 250, "mornings", _B + "Flat-pack furniture assembly, 5 years. Own tools."),
    WorkerSpec("dinesh", "Dinesh Babu", ("desk-assembly",), "HSR Layout", 10, 300, "afternoons", _B + "Office desks and workstations."),
    WorkerSpec("harpreet", "Harpreet Singh", ("shelf-assembly",), "BTM Layout", 10, 350, "mixed", _B + "Bookshelves, wall units and wall mounting."),
    WorkerSpec("joseph", "Joseph Thomas", ("desk-assembly", "shelf-assembly"), "Indiranagar", 10, 400, "evenings", _B + "Premium furniture and larger assemblies."),
    WorkerSpec("bhavna", "Bhavna Shah", ("shelf-assembly",), "Jayanagar", 5, 280, "weekend", _B + "Shelving and storage units."),
    WorkerSpec("tariq", "Tariq Ahmed", ("desk-assembly", "shelf-assembly"), "Bellandur", 15, 450, "fullday", _B + "Team of two available for bulk office assemblies."),
    # limited test cases that must NOT appear in public search
    WorkerSpec("restricted.a", "Restricted Test A", ("desk-assembly",), "Koramangala", 10, 200, "mornings", _B + "Restricted test account A (furniture): must never appear in search.", restricted=True),
    WorkerSpec("restricted.b", "Restricted Test B", ("basic-home-cleaning",), "HSR Layout", 10, 180, "mornings", _B + "Restricted test account B (cleaning): must never appear in search.", restricted=True),
)


@dataclass(frozen=True)
class OrgSpec:
    slug: str
    name: str
    org_type: str
    owner: str
    admins: tuple[str, ...] = ()
    members: tuple[str, ...] = ()
    policy: dict | None = None
    policy_id: str | None = None


_NOTE = "Demo example for the judge demonstration. Not official SAHAKAR–SEVA pricing."
BRIGHTDESK_POLICY = {
    "label": "Demo example: BrightDesk fixed business booking fee",
    "description": _NOTE + " The organization pays a fixed fee per booking; workers receive the full service price.",
    "is_example": True, "max_total_charge_bps": 1500,
    "components": [{"code": "business_booking_fee", "kind": "platform_fee", "label": "Business booking fee", "bearer": "business",
                    "fixed_paise": 4000, "organization_bookings": "only"}],
}
SAHYOG_POLICY = {
    "label": "Demo example: Sahyog hybrid fee with launch promotion",
    "description": _NOTE + " Worker-borne 4% + ₹5 (min ₹15, max ₹150); organization-borne ₹10 convenience fee, waived for services up to ₹2,000.",
    "is_example": True, "max_total_charge_bps": 1500,
    "components": [
        {"code": "platform_service_fee", "kind": "platform_fee", "label": "Platform service fee", "bearer": "worker",
         "percent_bps": 400, "fixed_paise": 500, "min_paise": 1500, "max_paise": 15000},
        {"code": "coop_convenience_fee", "kind": "platform_fee", "label": "Cooperative convenience fee", "bearer": "business",
         "fixed_paise": 1000, "organization_bookings": "only"},
    ],
    "promotions": [{"code": "coop_launch_waiver", "label": "Demo launch promotion: no convenience fee on services up to ₹2,000",
                    "waives": ["coop_convenience_fee"], "ends_at": "2027-12-31T23:59:59+05:30", "max_service_price_paise": 200000}],
}
ORGS: tuple[OrgSpec, ...] = (
    OrgSpec("brightdesk", "BrightDesk Co-working (Demo)", "business", "vikram", admins=("deepa",), policy=BRIGHTDESK_POLICY, policy_id="demo-brightdesk-terms"),
    OrgSpec("sahyog", "Sahyog Residents Cooperative (Demo)", "cooperative", "meena", admins=("imran",), members=("sunita",), policy=SAHYOG_POLICY, policy_id="demo-sahyog-terms"),
    OrgSpec("lakeside", "Lakeside Café & Bakery (Demo)", "business", "arjun"),
)


@dataclass(frozen=True)
class JobSpec:
    slug: str
    title: str
    description: str
    skill: str
    poster: str
    org: str | None
    locality: str
    day: int
    hh: int
    mm: int
    hours: float
    budget_rupees: int
    applicants: tuple[str, ...] = ()
    outcome: str = "open"                 # open | cancelled | requested | confirmed | completed
    selected: str | None = None
    showcase: str | None = None
    expect_model: str = "percentage"


JOBS: tuple[JobSpec, ...] = (
    # --- filled jobs (booking history) ---
    JobSpec("office-desks-done", "Assemble two office desks", "Two flat-pack desks for a home office; tools are available on site.", "desk-assembly", "karthik", None, "HSR Layout", -4, 10, 0, 3, 700, ("dinesh", "joseph", "ravi"), "completed", "dinesh"),
    JobSpec("brightdesk-shelving-done", "Reassemble and tighten office shelving", "Monthly maintenance of shelving units in the co-working space.", "shelf-assembly", "vikram", "brightdesk", "Koramangala", -10, 10, 0, 4, 1200, ("harpreet", "tariq"), "completed", "harpreet", "org-fixed-fee", "fixed"),
    JobSpec("brightdesk-cleaning-booked", "Fortnightly office cleaning", "Recurring cleaning for the co-working floor (second occurrence).", "basic-home-cleaning", "vikram", "brightdesk", "Koramangala", 5, 18, 0, 3, 1800, ("fatima", "lakshmi"), "confirmed", "fatima", None, "fixed"),
    JobSpec("sahyog-hall-done", "Assemble tables and chairs for the community hall", "Assembly of folding tables and chairs ahead of a residents' meeting.", "desk-assembly", "meena", "sahyog", "HSR Layout", -12, 10, 0, 4, 1500, ("ravi", "dinesh"), "completed", "ravi", "org-hybrid-promo", "hybrid"),
    JobSpec("sahyog-garden-done", "Society garden bed maintenance", "Seasonal clean-up of shared garden beds.", "garden-maintenance", "meena", "sahyog", "BTM Layout", -9, 9, 0, 5, 3000, ("prakash", "manjunath"), "completed", "prakash", "org-hybrid-above-cap", "hybrid"),
    JobSpec("sahyog-kitchen-pending", "Deep-clean the community kitchen", "Deep clean before the festival season.", "kitchen-cleaning", "meena", "sahyog", "HSR Layout", 4, 14, 0, 4, 2400, ("sunil", "lakshmi"), "requested", "sunil", None, "hybrid"),
    # --- open jobs the seeded workers can find ---
    JobSpec("wardrobe-desk", "Assemble a flat-pack wardrobe and desk", "One wardrobe and one study desk, all parts and instructions on site.", "desk-assembly", "karthik", None, "Koramangala", 3, 10, 0, 3, 900, ("ravi", "dinesh", "joseph")),
    JobSpec("kitchen-2bhk", "Deep clean 2BHK kitchen and hob", "Degrease cabinets, hob and chimney; supplies provided.", "kitchen-cleaning", "deepa", None, "HSR Layout", 2, 14, 0, 3, 1100, ("lakshmi", "sunil", "geeta")),
    JobSpec("hedges-lawn", "Trim hedges and mow a small lawn", "Front-yard hedge trim and lawn mow; garden waste to be bagged.", "garden-maintenance", "imran", None, "BTM Layout", 4, 9, 0, 2, 850, ("prakash", "manjunath", "zainab")),
    JobSpec("balcony-repot", "Repot balcony plants and set up a drip line", "About 12 pots to repot and a small drip-irrigation setup.", "plant-care", "sunita", None, "Jayanagar", 5, 10, 0, 2, 600, ("shanti", "anita", "manjunath")),
    JobSpec("three-bookshelves", "Assemble three bookshelves", "Three identical bookshelves; wall mounting not needed.", "shelf-assembly", "nandini", None, "Indiranagar", 3, 15, 0, 3, 1050, ("harpreet", "tariq")),
    JobSpec("standing-desks", "Assemble six standing desks", "Six electric standing desks for the co-working space.", "desk-assembly", "vikram", "brightdesk", "Koramangala", 6, 9, 0, 6, 2700, ("ravi", "dinesh", "tariq"), expect_model="fixed"),
    JobSpec("weekly-office-clean", "Weekly office cleaning (recurring request)", "Evening cleaning of a co-working floor; can become a regular booking.", "basic-home-cleaning", "vikram", "brightdesk", "Koramangala", 2, 18, 0, 3, 1500, ("lakshmi", "fatima", "geeta"), expect_model="fixed"),
    JobSpec("courtyard-cleanup", "Monsoon garden clean-up for the society courtyard", "Clear fallen leaves and re-edge beds in the shared courtyard.", "garden-maintenance", "meena", "sahyog", "Bellandur", 5, 9, 0, 4, 2000, ("gopal", "prakash", "zainab"), expect_model="hybrid"),
    JobSpec("notice-boards", "Assemble notice boards and shelves for the community hall", "Wall-mounted shelving and notice boards.", "shelf-assembly", "imran", "sahyog", "HSR Layout", 7, 11, 0, 3, 1800, ("harpreet", "tariq"), expect_model="hybrid"),
    JobSpec("cafe-kitchen", "Deep-clean the café kitchen after hours", "Evening deep clean of a small café kitchen.", "kitchen-cleaning", "arjun", "lakeside", "Indiranagar", 3, 19, 0, 3, 1600, ("mary", "rohan", "lakshmi")),
    JobSpec("cafe-herbs", "Maintain the herb garden and planters", "Weekly watering and pruning of café planters.", "plant-care", "arjun", "lakeside", "Indiranagar", 4, 8, 0, 2, 700, ("anita", "shanti")),
    JobSpec("study-desk", "Assemble a study desk", "One desk, 2 hours, tools available.", "desk-assembly", "asha", None, "HSR Layout", 2, 11, 0, 2, 800, ("dinesh", "ravi")),
    JobSpec("patio-cancelled", "Assemble patio furniture (cancelled)", "Posted and then cancelled by the poster.", "desk-assembly", "arjun", "lakeside", "Indiranagar", 6, 10, 0, 3, 1300, (), "cancelled"),
)


@dataclass(frozen=True)
class DirectSpec:
    key: str
    worker: str
    customer: str
    skill: str
    locality: str                    # customer location (must be inside the worker's radius)
    slot: SlotSpec | None            # None => "in progress now" slot
    target: str                      # requested | confirmed | in_progress | completed | cancelled | declined | disputed
    unit: str = "Flat 12"
    repeat_of: str | None = None
    dispute_category: str | None = None
    dispute_text: str | None = None
    resolve_with_reversal: bool = False
    showcase: str | None = None
    expect_model: str = "percentage"
    note: str | None = None


DIRECT: tuple[DirectSpec, ...] = (
    DirectSpec("headline", "ravi", "asha", "desk-assembly", "HSR Layout", SlotSpec("past-headline", -3, 10, 0, 2), "completed", "Flat 4B", showcase="headline-percentage", note="₹250/h × 2 h"),
    DirectSpec("repeat-rebook", "ravi", "asha", "desk-assembly", "HSR Layout", SlotSpec("rebook", 7, 10, 0, 2), "confirmed", "Flat 4B", repeat_of="headline", showcase="repeat-booking"),
    DirectSpec("kitchen-deep-clean", "lakshmi", "karthik", "kitchen-cleaning", "Koramangala", SlotSpec("past-kitchen", -5, 9, 0, 3), "completed", "House 21"),
    DirectSpec("garden-in-progress", "manjunath", "deepa", "garden-maintenance", "Jayanagar", None, "in_progress", "Villa 3"),
    DirectSpec("shelf-confirmed", "harpreet", "imran", "shelf-assembly", "BTM Layout", SlotSpec("confirmed", 8, 11, 0, 3), "confirmed", "Flat 9"),
    DirectSpec("desk-pending", "dinesh", "sunita", "desk-assembly", "HSR Layout", SlotSpec("pending", 7, 14, 0, 2), "requested", "Flat 17"),
    DirectSpec("plant-cancelled", "shanti", "nandini", "plant-care", "Koramangala", SlotSpec("cancelled", 8, 10, 0, 2), "cancelled", "Flat 2C"),
    DirectSpec("garden-declined", "zainab", "arjun", "garden-maintenance", "HSR Layout", SlotSpec("declined", 9, 10, 0, 2), "declined", "Unit 6"),
    DirectSpec("dispute-open", "joseph", "vikram", "desk-assembly", "Indiranagar", SlotSpec("past-dispute-open", -6, 10, 0, 4), "disputed", "Suite 5",
               dispute_category="unexpected_deduction", dispute_text="Demo dispute: I believe the worker's share shown to the worker looks lower than agreed. Please review the receipt."),
    DirectSpec("dispute-reversal", "tariq", "karthik", "shelf-assembly", "Bellandur", SlotSpec("past-dispute-reversal", -8, 10, 0, 3), "disputed", "Flat 8",
               dispute_category="worker_payout_differs", dispute_text="Demo dispute: the payout recorded for this job does not match what we agreed.",
               resolve_with_reversal=True, showcase="reversal-dispute"),
)

SHOWCASE_LABELS = {
    "headline-percentage": ("Headline booking: percentage fee", "Direct hire, default policy: the worker bears a percentage fee."),
    "org-fixed-fee": ("Organization job: fixed business fee", "Organization terms: a fixed fee billed to the organization; the worker receives the full service price."),
    "org-hybrid-promo": ("Organization job: hybrid fee with promotion", "Percentage + fixed worker fee with min/max, plus a convenience fee that a promotion waives."),
    "org-hybrid-above-cap": ("Organization job: hybrid fee, promotion not applicable", "Same hybrid policy; the service price is above the promotion's limit, so the convenience fee applies."),
    "repeat-booking": ("Repeat booking", "A customer books the same worker again: a new booking and a new quote."),
    "reversal-dispute": ("Dispute with ledger reversal", "A reviewer's decision recorded as a reversing ledger transaction; the original entries remain."),
}
