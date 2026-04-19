import logging
import re
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

try:
    from backend.services.backtest_service import run_backtest
except ImportError:
    from services.backtest_service import run_backtest

router = APIRouter(prefix="/backtest", tags=["backtest"])

_ALLOWED_TIMEFRAMES = {
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w",
}


class BacktestRequest(BaseModel):
    symbol: str = Field(..., example="BTC/USDT")
    timeframe: str = Field(..., example="1h")
    start_date: str = Field(..., example="2025-01-01T00:00:00Z")
    strategy_params: Dict[str, Any] = Field(
        default_factory=dict,
        example={"strategy": "close_above_ma", "period": 20, "threshold": 0.0},
    )

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        # 只允許標準 BASE/QUOTE 格式，防止非預期字元傳入外部 API
        if not re.match(r'^[A-Z0-9]{2,10}/[A-Z0-9]{2,10}$', v.strip().upper()):
            raise ValueError("symbol 格式無效，請使用 'BASE/QUOTE' 格式，例如 'BTC/USDT'")
        return v.strip().upper()

    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, v: str) -> str:
        if v not in _ALLOWED_TIMEFRAMES:
            raise ValueError(
                f"timeframe 無效，允許的值: {', '.join(sorted(_ALLOWED_TIMEFRAMES))}"
            )
        return v


@router.post("/run")
async def run_backtest_endpoint(request: BacktestRequest):
    """執行回測並回傳績效結果。"""

    try:
        result = run_backtest(
            symbol=request.symbol,
            timeframe=request.timeframe,
            start_date=request.start_date,
            strategy_params=request.strategy_params,
        )
    except Exception as exc:
        logger.exception("回測執行期間發生未預期錯誤")
        raise HTTPException(status_code=500, detail="Internal server error") from exc

    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])

    return result
