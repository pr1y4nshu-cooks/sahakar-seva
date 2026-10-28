"""Trust-ledger routes (docs/contracts/TRUST_LEDGER_API_CONTRACT.md). Registered before the MVP marketplace
routers so ``/bookings/{id}/quote-revisions`` is not captured by ``/bookings/{id}/{action}``."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.error_handler import ContractCompliantRoute
from app.api.v1.marketplace import errors, me
from app.core.config import get_settings
from app.core.errors import ApiError, conflict, forbidden, not_found
from app.db.session import get_db
from app.models.marketplace import Booking
from app.models.trust import AnchorCheckpoint
from app.models.user import User
from app.repositories import marketplace_repository as mrepo
from pydantic import ValidationError
from sqlalchemy import func

from app.api.v1.marketplace import optional_me
from app.models.marketplace import Job, Settlement
from app.schemas.marketplace import BookingRead, PricingPreviewRequest, PricingSimulateRequest, QuoteRevisionCreate
from app.services import fee_policy_service as fps
from app.services.marketplace_common import managed_organization_ids
from app.services import booking_service, dispute_service, insights_service
from app.services import trust_service as trust
from app.trust import integrity
from app.trust.anchoring import STATUS_LABELS
from app.trust.timestamping import ca_fingerprint

R = dict(route_class=ContractCompliantRoute)

public = APIRouter(tags=["trust (public)"], **R)


@public.get("/fee-policy", responses=errors(), summary="The ACTIVE default fee policy (authoritative; read from the fee_policies table)")
def get_fee_policy(db: Session = Depends(get_db)) -> dict:
    return trust.fee_policy(db)


@public.get("/fee-policies", responses=errors(), summary="History of default fee policy versions (active and retired)")
def fee_policy_history(db: Session = Depends(get_db)) -> list[dict]:
    return trust.fee_policy_history(db)


def _org_for(db: Session, user: User | None, organization_id: UUID | None) -> UUID | None:
    if organization_id is None:
        return None
    if user is None:
        raise ApiError(401, "AUTH_REQUIRED", "Sign in to see an organization's fee terms.")
    if organization_id not in managed_organization_ids(db, user.id):
        raise not_found("Organization not found.")
    return organization_id


@public.get("/fee-policy/applicable", responses=errors(401, 404), summary="The policy that would price a new booking for you / your organization")
def applicable_policy(organization_id: UUID | None = None, db: Session = Depends(get_db), user: User | None = Depends(optional_me)) -> dict:
    org = _org_for(db, user, organization_id)
    fp = fps.active_policy(db, org)
    if fp is None:
        raise fps.NoActivePolicyError()
    return fps.policy_view(fp) | {"applies_because": "organization-specific terms" if fp.organization_id else "default policy"}


@public.post("/pricing/preview", responses=errors(401, 404, 422, 503), summary="Price breakdown under the active policy (no booking is created)")
def pricing_preview(payload: PricingPreviewRequest, db: Session = Depends(get_db), user: User | None = Depends(optional_me)) -> dict:
    return trust.preview(db, payload.service_price_paise, payload.origin, _org_for(db, user, payload.organization_id))


@public.post("/pricing/simulate", responses=errors(401, 403, 422), summary="Evaluate a candidate fee policy (nothing is stored)")
def pricing_simulate(payload: PricingSimulateRequest, db: Session = Depends(get_db), user: User | None = Depends(optional_me)) -> dict:
    recorded = None
    if payload.include_recorded_bookings:
        if user is None or not dispute_service.is_reviewer(db, user):
            raise forbidden("Re-pricing recorded bookings is limited to platform staff.")
        rows = db.execute(
            select(Booking.id, Booking.origin, Job.organization_id)
            .join(Settlement, Settlement.booking_id == Booking.id)
            .outerjoin(Job, Job.id == Booking.job_id)
        ).all()
        recorded = []
        for booking_id, origin, org in rows:
            q = trust.current_quote(db, booking_id)
            booking = db.get(Booking, booking_id)
            recorded.append((trust.service_price(q) if q else booking.price_paise, origin, org is not None))
    try:
        return trust.simulate(payload.definition, payload.sample_service_prices_paise, payload.origin, payload.for_organization, recorded)
    except (ValidationError, ValueError) as exc:
        raise ApiError(422, "INVALID_FEE_POLICY", str(exc)[:1500]) from exc


@public.get("/trust/anchoring", responses=errors(), summary="External timestamping configuration and status meanings")
def anchoring_config() -> dict:
    s = get_settings()
    return {
        "tsa_configured": s.tsa_configured,
        "tsa_name": (s.tsa_name or s.tsa_url) if s.tsa_configured else None,
        "tsa_url": s.tsa_url if s.tsa_configured else None,
        "trust_anchor_sha256": ca_fingerprint(s.tsa_ca_file) if s.tsa_configured else None,
        "protocol": "RFC 3161",
        "data_sent": "Only the 32-byte SHA-256 checkpoint digest and a random nonce.",
        "statuses": STATUS_LABELS,
    }


def _checkpoint_public(cp: AnchorCheckpoint, include_token: bool) -> dict:
    out = {
        "checkpoint_id": cp.id, "checkpoint_index": cp.checkpoint_index, "first_sequence": cp.first_sequence,
        "last_sequence": cp.last_sequence, "event_count": cp.event_count, "merkle_root": cp.merkle_root,
        "last_event_hash": cp.last_event_hash, "previous_checkpoint_digest": cp.previous_checkpoint_digest,
        "digest": cp.digest, "body_canonical": cp.body_canonical, "created_at": cp.created_at,
        "anchor_status": cp.anchor_status, "anchor_status_label": STATUS_LABELS[cp.anchor_status],
        "tsa_name": cp.tsa_name, "tsa_gen_time": cp.tsa_gen_time, "attempt_count": cp.attempt_count,
        "last_error": cp.last_error,
    }
    if include_token:
        out["time_stamp_response_der_b64"] = cp.tsa_response_b64
        out["request_nonce"] = cp.request_nonce
    return out


@public.get("/trust/checkpoints", responses=errors(), summary="Public checkpoint digests (hashes only, no personal data)")
def list_checkpoints(limit: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(AnchorCheckpoint).order_by(AnchorCheckpoint.checkpoint_index.desc()).limit(limit))
    return [_checkpoint_public(cp, include_token=False) for cp in rows]


@public.get("/trust/checkpoints/{checkpoint_index}", responses=errors(404), summary="One checkpoint with its timestamp token")
def get_checkpoint(checkpoint_index: int, db: Session = Depends(get_db)) -> dict:
    cp = db.scalar(select(AnchorCheckpoint).where(AnchorCheckpoint.checkpoint_index == checkpoint_index))
    if cp is None:
        raise not_found("Checkpoint not found.")
    return _checkpoint_public(cp, include_token=True)


staff = APIRouter(tags=["trust (platform staff)"], **R)


@staff.get("/trust/integrity", responses=errors(401, 403, 503), summary="Full chain/checkpoint/ledger verification (reviewers only)")
def verify_integrity(user: User = Depends(me), db: Session = Depends(get_db)) -> dict:
    if not dispute_service.is_reviewer(db, user):
        raise forbidden("Only platform staff can run a full integrity check.")
    return integrity.verify_database(db)


@staff.get("/economics/summary", responses=errors(401, 403, 503), summary="Recorded demo unit economics (reviewers only)")
def economics(user: User = Depends(me), db: Session = Depends(get_db)) -> dict:
    return insights_service.economics_summary(db, user)


bookings = APIRouter(prefix="/bookings", tags=["bookings: agreement & evidence"], **R)


def _party_booking(db: Session, user: User, booking_id: UUID) -> tuple[Booking, str]:
    booking = db.get(Booking, booking_id)
    role = booking_service._role(db, booking, user) if booking else None
    if booking is None or role is None:
        raise not_found("Booking not found.")
    return booking, role


@bookings.get("/{booking_id}/financial-record", responses=errors(401, 404, 503), summary="Quotes, acceptances, ledger and event chain for one booking")
def financial_record(booking_id: UUID, user: User = Depends(me), db: Session = Depends(get_db)) -> dict:
    booking, _ = _party_booking(db, user, booking_id)
    return trust.financial_record(db, booking)


@bookings.get("/{booking_id}/receipt", responses=errors(401, 404, 503), summary="Download the portable, offline-verifiable receipt")
def download_receipt(booking_id: UUID, user: User = Depends(me), db: Session = Depends(get_db)):
    booking, role = _party_booking(db, user, booking_id)
    body = trust.receipt(db, booking, role)
    return JSONResponse(
        body,
        headers={
            "Content-Disposition": f'attachment; filename="sahakar-receipt-{booking.id}.json"',
            "Cache-Control": "no-store",
        },
    )


@bookings.post("/{booking_id}/quote-revisions", response_model=BookingRead, status_code=201, responses=errors(401, 404, 409, 422, 503),
               summary="Propose a new quote version (either party, only while requested)")
def revise_quote(booking_id: UUID, payload: QuoteRevisionCreate, user: User = Depends(me), db: Session = Depends(get_db)):
    _, role = _party_booking(db, user, booking_id)
    booking = mrepo.lock_booking(db, booking_id)
    trust.revise_quote(db, booking, user, role, payload.service_price_paise)
    db.commit()
    return booking_service.get_booking(db, user, booking_id)


@bookings.post("/{booking_id}/quotes/{version}/accept", response_model=BookingRead, responses=errors(401, 404, 409, 503),
               summary="Accept one exact quote version")
def accept_quote_version(booking_id: UUID, version: int, user: User = Depends(me), db: Session = Depends(get_db)):
    _, role = _party_booking(db, user, booking_id)
    booking = mrepo.lock_booking(db, booking_id)
    if booking.status != "requested":
        raise conflict("PRICE_LOCKED", "This booking's price agreement is already final.")
    current = trust.current_quote(db, booking.id)
    if current is None or current.version != version:
        raise conflict("QUOTE_VERSION_MISMATCH", "Only the current quote version can be accepted.")
    if role == "worker":
        raise conflict("USE_BOOKING_ACCEPT", "Workers accept a quote by accepting the booking with this quote version.")
    trust.accept_quote(db, booking, current, user, role)
    db.commit()
    return booking_service.get_booking(db, user, booking_id)


@bookings.get("/{booking_id}/repeat-options", responses=errors(401, 404, 503), summary="Book the same worker again (new booking, new agreement)")
def repeat_options(booking_id: UUID, user: User = Depends(me), db: Session = Depends(get_db)) -> dict:
    return insights_service.repeat_options(db, user, booking_id)


organizations = APIRouter(prefix="/organizations", tags=["organizations: reporting"], **R)


@organizations.get("/{organization_id}/financial-summary", responses=errors(401, 404, 503), summary="Organization booking and spending summary (owner/admin)")
def org_summary(organization_id: UUID, user: User = Depends(me), db: Session = Depends(get_db)) -> dict:
    return insights_service.organization_summary(db, user, organization_id)


@organizations.get("/{organization_id}/financial-report.csv", responses=errors(401, 404, 503), summary="Organization booking records as CSV (owner/admin)")
def org_csv(organization_id: UUID, user: User = Depends(me), db: Session = Depends(get_db)) -> Response:
    content = insights_service.organization_csv(db, user, organization_id)
    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="sahakar-org-{organization_id}.csv"', "Cache-Control": "no-store"},
    )


ROUTERS = (public, staff, bookings, organizations)
