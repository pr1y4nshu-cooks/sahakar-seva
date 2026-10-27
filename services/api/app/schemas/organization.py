from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class OrganizationWithMyRole(BaseModel):
    id: UUID
    name: str
    organization_type: Literal["business", "cooperative"]
    my_membership_role: Literal["owner", "admin", "member"]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class OrganizationCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    organization_type: Literal["business", "cooperative"]

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        trimmed = v.strip()
        if len(trimmed) < 2 or len(trimmed) > 120:
            raise ValueError("Organization name must be between 2 and 120 characters after trimming")
        return trimmed

    model_config = ConfigDict(extra="forbid")
