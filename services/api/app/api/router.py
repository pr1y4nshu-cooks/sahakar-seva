from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.organizations import router as organizations_router
from app.api.v1.users import router as users_router
from app.api.v1.workers import router as workers_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(users_router)
api_router.include_router(workers_router)
api_router.include_router(organizations_router)
