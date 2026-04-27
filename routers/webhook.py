"""
Webhook endpoints for Supabase Database events.

Set up in Supabase Dashboard → Database → Webhooks:
  - Table  : auth.users
  - Events : UPDATE
  - URL    : https://your-backend.com/webhooks/user-registered
  - Headers: Authorization: Bearer <WEBHOOK_SECRET>

Fires a welcome email only when email_confirmed_at transitions
from NULL → non-NULL (i.e. the user just verified their email).
"""

import logging
import secrets

from fastapi import APIRouter, Header, HTTPException, Request

try:
    from backend.config import WEBHOOK_SECRET
    from backend.services.email_service import send_welcome_email
except ImportError:
    from config import WEBHOOK_SECRET
    from services.email_service import send_welcome_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _verify_secret(authorization: str | None) -> None:
    """Validate the shared Bearer secret sent by Supabase."""
    if not WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="WEBHOOK_SECRET not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.removeprefix("Bearer ")
    # Use constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(token, WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")


@router.post("/user-registered", status_code=200)
async def user_registered(
    request: Request,
    authorization: str | None = Header(default=None),
):
    """
    Called by Supabase DB webhook on UPDATE of auth.users.

    Only sends a welcome email when email_confirmed_at transitions
    from NULL (old_record) to non-NULL (record), meaning the user
    just clicked the confirmation link.

    Expected payload structure:
    {
      "type": "UPDATE",
      "table": "users",
      "schema": "auth",
      "record":     { "email": "...", "email_confirmed_at": "2026-04-26T...", ... },
      "old_record": { "email": "...", "email_confirmed_at": null, ... }
    }
    """
    _verify_secret(authorization)

    payload = await request.json()
    record = payload.get("record", {})
    old_record = payload.get("old_record", {})

    just_confirmed = (
        old_record.get("email_confirmed_at") is None
        and record.get("email_confirmed_at") is not None
    )

    if not just_confirmed:
        # Some other field was updated – ignore silently
        return {"message": "not an email confirmation, skipped"}

    email = record.get("email")
    if not email:
        logger.warning("Webhook payload missing email: %s", payload)
        return {"message": "no email in payload, skipped"}

    try:
        send_welcome_email(email)
        logger.info("Welcome email sent via webhook to %s", email)
    except Exception as exc:
        logger.error("Failed to send welcome email to %s: %s", email, exc)
        raise HTTPException(status_code=500, detail="Failed to send welcome email")

    return {"message": "welcome email sent"}
