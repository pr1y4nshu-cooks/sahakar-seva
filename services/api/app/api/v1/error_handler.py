from collections.abc import Callable
import logging
from typing import Any

from fastapi import Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.core.security import AuthException

logger = logging.getLogger(__name__)


class ContractCompliantRoute(APIRoute):
    """
    Route class ensuring all responses match the Phase 2 Technical Contract error format:
    {"error": {"code": "MACHINE_CODE", "message": "Human-readable message", "details": ...}}
    Leaves Phase 1 health endpoints unaffected.
    """

    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            try:
                return await original_route_handler(request)
            except RequestValidationError as exc:
                # Format validation errors cleanly without leaking sensitive internal details
                cleaned_errors = []
                for err in exc.errors():
                    cleaned_errors.append({
                        "loc": [str(loc) for loc in err.get("loc", [])],
                        "msg": err.get("msg", "Invalid value"),
                        "type": err.get("type", "value_error"),
                    })
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    content={
                        "error": {
                            "code": "VALIDATION_ERROR",
                            "message": "Invalid request payload or forbidden fields provided.",
                            "details": cleaned_errors,
                        }
                    },
                )
            except AuthException as exc:
                return JSONResponse(
                    status_code=exc.status_code,
                    content=exc.detail,
                )
            except Exception as exc:
                logger.error("Unhandled exception in API route %s: %s", request.url.path, exc, exc_info=True)
                return JSONResponse(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    content={
                        "error": {
                            "code": "INTERNAL_ERROR",
                            "message": "An unexpected server error occurred.",
                        }
                    },
                )

        return custom_route_handler
