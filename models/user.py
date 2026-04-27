"""Pydantic schemas for user-related endpoints."""

from typing import List, Optional

from pydantic import BaseModel, Field


class UserRegisterRequest(BaseModel):
    """Payload for user registration with email verification."""

    email: str = Field(..., min_length=5, max_length=320)
    password: str = Field(..., min_length=6, max_length=128)


class UserRegisterResponse(BaseModel):
    """Response returned after registration request is accepted."""

    message: str


class UserProfileUpdate(BaseModel):
    """Payload for creating / updating a user profile."""

    display_name: str = Field(..., min_length=1, max_length=100)
    trading_experience: str = Field(
        ...,
        pattern="^(beginner|intermediate|advanced)$",
    )
    interested_assets: List[str] = Field(default_factory=list)
    how_found_us: str = Field("", max_length=200)
    use_case: str = Field("", max_length=200)


class UserProfileResponse(BaseModel):
    """Shape returned by GET /user/profile."""

    id: str
    display_name: Optional[str] = None
    trading_experience: Optional[str] = None
    interested_assets: Optional[List[str]] = None
    how_found_us: Optional[str] = None
    use_case: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
