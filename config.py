"""
Centralised configuration & Supabase client factory.

Environment variables required:
  SUPABASE_URL              – Project URL (e.g. https://xxx.supabase.co)
  SUPABASE_SERVICE_ROLE_KEY – Service-role key (backend only, never expose)
  SUPABASE_JWT_SECRET       – JWT secret for local token verification
"""

import os
from functools import lru_cache

from supabase import Client, create_client

SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_JWT_SECRET: str = os.getenv("SUPABASE_JWT_SECRET", "")

RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")
RESEND_FROM_EMAIL: str = os.getenv("RESEND_FROM_EMAIL", "")
SIGNUP_EMAIL_REDIRECT_TO: str = os.getenv("SIGNUP_EMAIL_REDIRECT_TO", "")
FRONTEND_URL: str = os.getenv("FRONTEND_URL", "https://vizquant.com")

# Shared secret for validating Supabase DB webhooks (set the same value in
# the Supabase webhook "Authorization" header as "Bearer <this value>")
WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "")


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """Return a singleton Supabase client using the service-role key."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set"
        )
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
