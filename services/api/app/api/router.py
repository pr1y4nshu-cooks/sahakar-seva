from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.users import router as users_router, worker_profile_router, organization_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(users_router)
api_router.include_router(worker_profile_router)
api_router.include_router(organization_router)

