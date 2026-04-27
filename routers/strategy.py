"""
Strategy CRUD endpoints.

All operations are scoped to the authenticated user via RLS + explicit user_id filter.
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException

try:
    from backend.config import get_supabase_client
    from backend.dependencies import get_current_user
    from backend.models.strategy import StrategyCreate, StrategyResponse, StrategyUpdate
except ImportError:
    from config import get_supabase_client
    from dependencies import get_current_user
    from models.strategy import StrategyCreate, StrategyResponse, StrategyUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/strategies", tags=["strategies"])


def _get_owned_strategy(strategy_id: str, user_id: str):
    """Return strategy row or raise 404 if not found / not owned."""
    supabase = get_supabase_client()
    result = (
        supabase.table("strategies")
        .select("id")
        .eq("id", strategy_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return result.data


@router.get("", response_model=List[StrategyResponse])
async def list_strategies(user: dict = Depends(get_current_user)):
    """Return all strategies owned by the authenticated user, newest first."""
    supabase = get_supabase_client()
    result = (
        supabase.table("strategies")
        .select("*")
        .eq("user_id", user["id"])
        .order("updated_at", desc=True)
        .execute()
    )
    return result.data or []


@router.post("", response_model=StrategyResponse, status_code=201)
async def create_strategy(
    body: StrategyCreate,
    user: dict = Depends(get_current_user),
):
    """Save a new strategy for the authenticated user."""
    supabase = get_supabase_client()
    row = {"user_id": user["id"], **body.model_dump()}
    result = supabase.table("strategies").insert(row).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to save strategy")
    return result.data[0]


@router.patch("/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(
    strategy_id: str,
    body: StrategyUpdate,
    user: dict = Depends(get_current_user),
):
    """Rename or update fields of an owned strategy."""
    _get_owned_strategy(strategy_id, user["id"])

    update_data = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=422, detail="No fields to update")

    supabase = get_supabase_client()
    result = (
        supabase.table("strategies")
        .update(update_data)
        .eq("id", strategy_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to update strategy")
    return result.data[0]


@router.delete("/{strategy_id}", status_code=204)
async def delete_strategy(
    strategy_id: str,
    user: dict = Depends(get_current_user),
):
    """Delete an owned strategy."""
    _get_owned_strategy(strategy_id, user["id"])
    supabase = get_supabase_client()
    supabase.table("strategies").delete().eq("id", strategy_id).execute()
