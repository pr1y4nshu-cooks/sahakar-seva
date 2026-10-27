from datetime import datetime
from uuid import UUID
from typing import Optional, Literal

from pydantic import BaseModel, Field, EmailStr, ConfigDict


class UserBase(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=120)
    email: EmailStr


class UserCreate(UserBase):
    pass


class UserUpdate(BaseModel):
    display_name: Optional[str] = Field(None, min_length=1, max_length=120)


class UserResponse(UserBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkerProfileBase(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=120)
    bio: Optional[str] = None


class WorkerProfileCreate(WorkerProfileBase):
    pass


class WorkerProfileUpdate(BaseModel):
    display_name: Optional[str] = Field(None, min_length=1, max_length=120)
    bio: Optional[str] = None


class WorkerProfileResponse(WorkerProfileBase):
    id: UUID
    user_id: UUID
    onboarding_status: Literal["draft", "pending_review", "approved", "restricted"]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrganizationBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    organization_type: Literal["business", "cooperative"]


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationResponse(OrganizationBase):
    id: UUID
    my_membership_role: Literal["owner", "admin", "member"]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ErrorDetail(BaseModel):
    field: Optional[str] = None
    message: str


class ErrorResponseInner(BaseModel):
    code: str
    message: str
    details: Optional[list[ErrorDetail]] = None


class ErrorResponse(BaseModel):
    error: ErrorResponseInner