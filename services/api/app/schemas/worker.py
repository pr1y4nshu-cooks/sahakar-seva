from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class WorkerProfileRead(BaseModel):
    id: UUID
    user_id: UUID
    display_name: str
    bio: str | None = None
    onboarding_status: Literal["draft", "pending_review", "approved", "restricted"]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class WorkerProfileCreate(BaseModel):
    display_name: str = Field(..., min_length=2, max_length=80)
    bio: str | None = Field(default=None, max_length=500)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v: str) -> str:
        trimmed = v.strip()
        if len(trimmed) < 2 or len(trimmed) > 80:
            raise ValueError("display_name must be between 2 and 80 characters after trimming")
        return trimmed

    @field_validator("bio")
    @classmethod
    def validate_bio(cls, v: str | None) -> str | None:
        if v is not None and len(v) > 500:
            raise ValueError("bio must not exceed 500 characters")
        return v

    model_config = ConfigDict(extra="forbid")


class WorkerProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=80)
    bio: str | None = Field(default=None, max_length=500)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v: str | None) -> str | None:
        if v is not None:
            trimmed = v.strip()
            if len(trimmed) < 2 or len(trimmed) > 80:
                raise ValueError("display_name must be between 2 and 80 characters after trimming")
            return trimmed
        return v

    @field_validator("bio")
    @classmethod
    def validate_bio(cls, v: str | None) -> str | None:
        if v is not None and len(v) > 500:
            raise ValueError("bio must not exceed 500 characters")
        return v

    @model_validator(mode="before")
    @classmethod
    def check_at_least_one_field(cls, values: dict) -> dict:
        if not isinstance(values, dict) or len(values) == 0:
            raise ValueError("At least one field must be provided in PATCH update")
        # Check that at least one of the recognized fields is explicitly present in the input dict
        if "display_name" not in values and "bio" not in values:
            raise ValueError("At least one of 'display_name' or 'bio' must be provided")
        return values

    model_config = ConfigDict(extra="forbid")
