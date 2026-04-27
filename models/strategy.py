"""Pydantic schemas for strategy CRUD endpoints."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class StrategyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    symbol: str
    timeframe: str
    start_date: str
    strategy_params: Dict[str, Any] = Field(default_factory=dict)
    workspace_state: Optional[Dict[str, Any]] = None


class StrategyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    start_date: Optional[str] = None
    strategy_params: Optional[Dict[str, Any]] = None
    workspace_state: Optional[Dict[str, Any]] = None


class StrategyResponse(BaseModel):
    id: str
    user_id: str
    name: str
    symbol: str
    timeframe: str
    start_date: str
    strategy_params: Dict[str, Any]
    workspace_state: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
