"""
User-profile endpoints.

Authenticated users can read and upsert their own profile.
"""

import json
import logging
from urllib import error, request

from fastapi import APIRouter, Depends, HTTPException

try:
    from backend.config import (
        SIGNUP_EMAIL_REDIRECT_TO,
        SUPABASE_SERVICE_ROLE_KEY,
        SUPABASE_URL,
        get_supabase_client,
    )
    from backend.dependencies import get_current_user
    from backend.models.user import (
        UserProfileResponse,
        UserProfileUpdate,
        UserRegisterRequest,
        UserRegisterResponse,
    )
    from backend.services.email_service import (
        send_signup_verification_email,
        send_welcome_email,
    )
except ImportError:
    from config import (
        SIGNUP_EMAIL_REDIRECT_TO,
        SUPABASE_SERVICE_ROLE_KEY,
        SUPABASE_URL,
        get_supabase_client,
    )
    from dependencies import get_current_user
    from models.user import (
        UserProfileResponse,
        UserProfileUpdate,
        UserRegisterRequest,
        UserRegisterResponse,
    )
    from services.email_service import send_signup_verification_email, send_welcome_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user", tags=["user"])


def _extract_action_link(link_response: object) -> str | None:
    """Extract action_link from Supabase admin generate_link response shape."""
    if isinstance(link_response, dict):
        data = link_response.get("data")
        if isinstance(data, dict):
            return data.get("action_link")
        return link_response.get("action_link")

    data = getattr(link_response, "data", None)
    if isinstance(data, dict):
        return data.get("action_link")

    return getattr(link_response, "action_link", None)


def _generate_signup_link_via_rest(
    email: str,
    password: str,
    redirect_to: str | None = None,
) -> str:
    """Fallback to GoTrue admin REST API when SDK methods are unavailable."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("Supabase configuration missing")

    url = f"{SUPABASE_URL}/auth/v1/admin/generate_link"
    payload = {
        "type": "signup",
        "email": email,
        "password": password,
    }
    if redirect_to:
        payload["redirect_to"] = redirect_to
        payload["options"] = {"redirect_to": redirect_to}

    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json",
        },
    )

    try:
        with request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        error_text = exc.read().decode("utf-8", errors="ignore")
        msg = error_text or str(exc)
        if "already" in msg.lower() and "registered" in msg.lower():
            raise HTTPException(status_code=409, detail="This email is already registered")
        logger.error("Supabase generate_link failed: %s", msg)
        raise HTTPException(status_code=500, detail="Failed to register user")

    action_link = body.get("action_link")
    if not action_link:
        raise HTTPException(status_code=500, detail="Failed to create verification link")
    return action_link


def _generate_signup_verification_link(
    email: str,
    password: str,
    redirect_to: str | None = None,
) -> str:
    """Generate Supabase signup confirmation link (creates user if needed)."""
    supabase = get_supabase_client()

    payload = {
        "type": "signup",
        "email": email,
        "password": password,
    }
    if redirect_to:
        payload["redirect_to"] = redirect_to
        payload["options"] = {"redirect_to": redirect_to}

    try:
        link_response = supabase.auth.admin.generate_link(payload)
        action_link = _extract_action_link(link_response)
        if action_link:
            return action_link
    except Exception as exc:
        msg = str(exc)
        if "already" in msg.lower() and "registered" in msg.lower():
            raise HTTPException(status_code=409, detail="This email is already registered")
        logger.warning("SDK generate_link failed, fallback to REST: %s", msg)

    return _generate_signup_link_via_rest(email, password, redirect_to)


@router.post("/register", response_model=UserRegisterResponse, status_code=200)
async def register_user(body: UserRegisterRequest):
    """Register user and send the verification email through Resend."""
    # Always use server-configured redirect to prevent open-redirect attacks.
    target_redirect = SIGNUP_EMAIL_REDIRECT_TO or None
    verify_link = _generate_signup_verification_link(
        body.email,
        body.password,
        target_redirect,
    )

    try:
        send_signup_verification_email(body.email, verify_link)
    except Exception as exc:
        logger.error("Failed to send signup verification email to %s: %s", body.email, exc)
        raise HTTPException(status_code=500, detail="Failed to send verification email")

    return {"message": "Registration successful. Please check your email to verify your account."}


@router.get("/profile", response_model=UserProfileResponse)
async def get_profile(user: dict = Depends(get_current_user)):
    """Return the authenticated user's profile (or 404 if not created yet)."""
    supabase = get_supabase_client()
    result = (
        supabase.table("user_profiles")
        .select("*")
        .eq("id", user["id"])
        .maybe_single()
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Profile not found")

    return result.data


@router.put("/profile", response_model=UserProfileResponse)
async def upsert_profile(
    body: UserProfileUpdate,
    user: dict = Depends(get_current_user),
):
    """Create or update the authenticated user's profile."""
    supabase = get_supabase_client()

    row = {"id": user["id"], **body.model_dump()}
    result = supabase.table("user_profiles").upsert(row).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to save profile")

    return result.data[0]


@router.post("/welcome-email", status_code=200)
async def send_welcome_email_endpoint(user: dict = Depends(get_current_user)):
    """Send a welcome email to the authenticated user. Call once after registration."""
    email = user.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="User email not found")

    try:
        send_welcome_email(email)
    except Exception as exc:
        logger.error("Failed to send welcome email to %s: %s", email, exc)
        raise HTTPException(status_code=500, detail="Failed to send welcome email")

    return {"message": "Welcome email sent"}
