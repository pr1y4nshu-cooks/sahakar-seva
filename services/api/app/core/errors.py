"""HTTP errors for marketplace routes.

They subclass AuthException because ContractCompliantRoute renders that class as the contract
error envelope: {"error": {"code", "message", "details"}}.
"""

from typing import Any

from app.core.security import AuthException


class ApiError(AuthException):
    def __init__(self, status_code: int, code: str, message: str, details: Any = None):
        super().__init__(status_code=status_code, code=code, message=message, details=details)


def not_found(message: str = "The requested resource was not found.") -> ApiError:
    return ApiError(404, "RESOURCE_NOT_FOUND", message)


def forbidden(message: str = "You are not allowed to perform this action.") -> ApiError:
    return ApiError(403, "FORBIDDEN", message)


def conflict(code: str, message: str) -> ApiError:
    return ApiError(409, code, message)


def unprocessable(code: str, message: str, details: Any = None) -> ApiError:
    return ApiError(422, code, message, details)
