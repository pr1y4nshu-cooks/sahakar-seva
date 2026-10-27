"""OpenAPI error-response declarations for Phase 2 protected routes (DOC-01).

Documentation only: runtime behaviour is produced by ContractCompliantRoute and AuthException.
Each route declares exactly the failure codes listed in docs/contracts/phase2.openapi.yaml.
"""

from typing import Any

from app.schemas.error import ErrorResponse

_DESCRIPTIONS: dict[int, str] = {
    401: "Authentication missing, expired, or invalid (AUTH_REQUIRED / INVALID_TOKEN)",
    404: "Resource not found (RESOURCE_NOT_FOUND)",
    409: "Conflict (IDENTITY_CONFLICT / WORKER_PROFILE_EXISTS)",
    422: "Validation error or forbidden fields (VALIDATION_ERROR)",
    503: "Auth provider unavailable or not configured (AUTH_PROVIDER_UNAVAILABLE / AUTH_NOT_CONFIGURED)",
}


def error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    return {code: {"model": ErrorResponse, "description": _DESCRIPTIONS[code]} for code in status_codes}
