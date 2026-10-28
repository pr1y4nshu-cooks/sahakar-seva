"""Public overview / open-jobs board and the development-only demo guide (see app/services/demo_service.py)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.v1.error_handler import ContractCompliantRoute
from app.api.v1.marketplace import errors
from app.db.session import get_db
from app.services import demo_service

R = dict(route_class=ContractCompliantRoute)
router = APIRouter(tags=["marketplace overview & demo"], **R)


@router.get("/marketplace/overview", responses=errors(503), summary="Public counts: available workers, categories, open jobs (+ sample-data label)")
def marketplace_overview(db: Session = Depends(get_db)) -> dict:
    return demo_service.overview(db)


@router.get("/jobs/open", responses=errors(422, 503), summary="Public board of open jobs (no addresses, no personal data)")
def open_jobs(skill_id: UUID | None = None, locality: str | None = Query(default=None, max_length=120), sample_only: bool = False,
              limit: int = Query(default=60, ge=1, le=100), db: Session = Depends(get_db)) -> list[dict]:
    return demo_service.open_jobs(db, skill_id, locality, limit, sample_only)


@router.get("/demo/guide", responses=errors(404), summary="Demo guide: personas, recommended flow, showcase bookings (development only)")
def demo_guide(db: Session = Depends(get_db)) -> dict:
    return demo_service.guide(db)


@router.get("/demo/showcase/{key}/receipt", responses=errors(404), summary="Receipt of a synthetic showcase booking (development only)")
def showcase_receipt(key: str, db: Session = Depends(get_db)):
    return JSONResponse(demo_service.showcase_receipt(db, key), headers={"Cache-Control": "no-store"})
