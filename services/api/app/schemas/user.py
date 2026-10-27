from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserRead(BaseModel):
    id: UUID
    display_name: str
    email: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class UserUpdate(BaseModel):
    display_name: str = Field(..., min_length=2, max_length=80)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v: str) -> str:
        trimmed = v.strip()
        if len(trimmed) < 2 or len(trimmed) > 80:
            raise ValueError("display_name must be between 2 and 80 characters after trimming")
        return trimmed

    model_config = ConfigDict(extra="forbid")
