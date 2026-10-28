from fastapi import APIRouter

from app.api.v1.demo import router as demo_router
from app.api.v1.health import router as health_router
from app.api.v1.marketplace import ROUTERS as marketplace_routers
from app.api.v1.organizations import router as organizations_router
from app.api.v1.trust import ROUTERS as trust_routers
from app.api.v1.users import router as users_router
from app.api.v1.workers import router as workers_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(users_router)
api_router.include_router(workers_router)
api_router.include_router(organizations_router)
api_router.include_router(demo_router)  # /jobs/open must precede /jobs/{job_id}
# Trust routes first: /bookings/{id}/quote-revisions must not be captured by /bookings/{id}/{action}.
for _router in trust_routers:
    api_router.include_router(_router)
for _router in marketplace_routers:
    api_router.include_router(_router)
