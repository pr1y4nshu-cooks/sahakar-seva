from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class ErrorDetail(BaseModel):
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error description")
    details: dict[str, Any] | list[Any] | None = Field(default=None, description="Optional extra error details")

    model_config = ConfigDict(extra="forbid")


class ErrorResponse(BaseModel):
    error: ErrorDetail

    model_config = ConfigDict(extra="forbid")
