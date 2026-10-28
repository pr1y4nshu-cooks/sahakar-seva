import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging

configure_logging()
settings = get_settings()
log = logging.getLogger("sahakar.anchoring")


async def _anchor_worker() -> None:
    """Checkpoint new financial events and submit due checkpoints to the configured TSA.

    Runs outside every request transaction; booking completion never waits for it.
    """
    from app.db.session import SessionLocal
    from app.trust.anchoring import run_cycle

    while True:
        try:
            result = await asyncio.to_thread(run_cycle, SessionLocal, settings)
            if result["created_checkpoint"] or result["anchoring"]:
                log.info("anchor cycle: %s", result)
        except Exception:  # noqa: BLE001 - keep the loop alive; state stays in the outbox rows
            log.exception("anchor cycle failed")
        await asyncio.sleep(settings.anchor_worker_interval_seconds)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(_anchor_worker()) if settings.anchor_worker_enabled else None
    try:
        yield
    finally:
        if task:
            task.cancel()


app = FastAPI(title="SAHAKAR–SEVA API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)
