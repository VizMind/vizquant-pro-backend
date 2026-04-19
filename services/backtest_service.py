import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

import ccxt
import pandas as pd
import vectorbt as vbt

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parents[1] / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL = pd.Timedelta(hours=24)


def _get_cache_path(symbol: str, timeframe: str, exchange_id: str) -> Path:
    safe_symbol = symbol.replace("/", "_").replace(" ", "_").replace(":", "_")
    safe_timeframe = timeframe.replace("/", "_").replace(" ", "_")
    filename = f"{exchange_id}_{safe_symbol}_{safe_timeframe}.csv"
    return CACHE_DIR / filename


def _is_cache_valid(cache_path: Path) -> bool:
    if not cache_path.exists():
        return False
    cache_age = pd.Timestamp.utcnow() - pd.Timestamp(cache_path.stat().st_mtime, unit="s", tz="UTC")
    return cache_age <= CACHE_TTL


def _save_cache(df: pd.DataFrame, cache_path: Path) -> None:
    df.to_csv(cache_path)


def _load_cache(cache_path: Path) -> pd.DataFrame:
    df = pd.read_csv(cache_path, parse_dates=["timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df.set_index("timestamp", inplace=True)
    return df


def _parse_start_date(start_date: str) -> int:
    try:
        dt = pd.to_datetime(start_date, utc=True)
        return int(dt.value // 10**6)
    except Exception as exc:
        raise ValueError(
            f"起始日期格式錯誤，請使用 ISO 格式字串，例如 '2024-01-01T00:00:00Z'。收到: {start_date}"
        ) from exc


def _convert_timeframe_to_timedelta(timeframe: str) -> pd.Timedelta:
    try:
        return pd.Timedelta(timeframe)
    except Exception as exc:
        raise ValueError(
            f"時間週期格式錯誤，請使用 pandas 可解析的時間字串，例如 '1h', '15m', '1d'。收到: {timeframe}"
        ) from exc


StrategyFunction = Callable[[pd.DataFrame, Dict[str, Any]], Tuple[pd.Series, pd.Series, Dict[str, Any]]]


def _strategy_close_above_ma(
    price_df: pd.DataFrame, strategy_params: Dict[str, Any]
) -> Tuple[pd.Series, pd.Series, Dict[str, Any]]:
    period = int(strategy_params.get("period", 20))
    threshold = float(strategy_params.get("threshold", 0.0))

    if period < 1:
        raise ValueError("period 必須為正整數。")

    ma = price_df["close"].rolling(window=period, min_periods=1).mean()
    if threshold == 0.0:
        entries = price_df["close"] > ma
        exits = price_df["close"] <= ma
    else:
        entries = price_df["close"] > ma * (1 + threshold)
        exits = price_df["close"] <= ma * (1 + threshold)

    price_df[f"ma_{period}"] = ma
    return entries, exits, {"period": period, "threshold": threshold}


def _calculate_rsi(close: pd.Series, period: int) -> pd.Series:
    """以 Wilder 平滑法計算 RSI。"""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50.0)


def _strategy_rsi(
    price_df: pd.DataFrame, strategy_params: Dict[str, Any]
) -> Tuple[pd.Series, pd.Series, Dict[str, Any]]:
    period = int(strategy_params.get("period", 14))
    threshold = float(strategy_params.get("threshold", 30.0))

    if period < 1:
        raise ValueError("period 必須為正整數。")

    rsi = _calculate_rsi(price_df["close"], period)
    price_df[f"rsi_{period}"] = rsi

    entries = rsi < threshold
    exits = rsi >= threshold

    return entries, exits, {"period": period, "threshold": threshold}


def _calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """計算指數移動平均線 (EMA)。"""
    return series.ewm(span=period, adjust=False).mean()


def _strategy_macd(
    price_df: pd.DataFrame, strategy_params: Dict[str, Any]
) -> Tuple[pd.Series, pd.Series, Dict[str, Any]]:
    fast_period = int(strategy_params.get("fast_period", 12))
    slow_period = int(strategy_params.get("slow_period", 26))
    signal_period = int(strategy_params.get("signal_period", 9))

    if fast_period < 1 or slow_period < 1 or signal_period < 1:
        raise ValueError("MACD 週期參數必須為正整數。")
    if fast_period >= slow_period:
        raise ValueError("MACD fast_period 必須小於 slow_period。")

    close = price_df["close"]
    ema_fast = _calculate_ema(close, fast_period)
    ema_slow = _calculate_ema(close, slow_period)
    macd_line = ema_fast - ema_slow
    signal_line = _calculate_ema(macd_line, signal_period)

    price_df["macd"] = macd_line
    price_df["macd_signal"] = signal_line
    price_df["macd_hist"] = macd_line - signal_line

    # 金叉買入：MACD 上穿 Signal；死叉賣出：MACD 下穿 Signal
    entries = (macd_line > signal_line) & (macd_line.shift(1) <= signal_line.shift(1))
    exits = (macd_line < signal_line) & (macd_line.shift(1) >= signal_line.shift(1))
    entries = entries.fillna(False)
    exits = exits.fillna(False)

    return entries, exits, {
        "fast_period": fast_period,
        "slow_period": slow_period,
        "signal_period": signal_period,
    }


def _strategy_bollinger_bands(
    price_df: pd.DataFrame, strategy_params: Dict[str, Any]
) -> Tuple[pd.Series, pd.Series, Dict[str, Any]]:
    period = int(strategy_params.get("period", 20))
    std_dev = float(strategy_params.get("std_dev", 2.0))

    if period < 1:
        raise ValueError("布林通道 period 必須為正整數。")
    if std_dev <= 0:
        raise ValueError("布林通道 std_dev 必須為正數。")

    close = price_df["close"]
    middle = close.rolling(window=period, min_periods=1).mean()
    std = close.rolling(window=period, min_periods=1).std(ddof=0)
    lower = middle - std_dev * std
    upper = middle + std_dev * std

    price_df["bb_middle"] = middle
    price_df["bb_upper"] = upper
    price_df["bb_lower"] = lower

    # 收盤價跌破下軌（超賣）→ 買入；收盤價突破上軌（超買）→ 賣出
    entries = close < lower
    exits = close > upper

    return entries, exits, {"period": period, "std_dev": std_dev}


def _strategy_combine(
    price_df: pd.DataFrame, strategy_params: Dict[str, Any]
) -> Tuple[pd.Series, pd.Series, Dict[str, Any]]:
    """將多個子策略條件以 AND / OR 組合，回傳合併後的進出場訊號。"""
    operator = strategy_params.get("operator", "and").lower()
    conditions: list = strategy_params.get("conditions") or []

    if not conditions:
        raise ValueError("邏輯組合積木需要至少一個子條件。")

    all_entries: list[pd.Series] = []
    all_exits: list[pd.Series] = []

    for cond in conditions:
        if not cond or not isinstance(cond, dict):
            continue
        sub_name = cond.get("strategy")
        if sub_name == "combine":
            raise ValueError("邏輯組合積木不支援巢狀使用。")
        if sub_name not in STRATEGY_REGISTRY:
            raise ValueError(f"不支援的子策略: {sub_name}")
        sub_entries, sub_exits, _ = STRATEGY_REGISTRY[sub_name](price_df, cond)
        all_entries.append(sub_entries)
        all_exits.append(sub_exits)

    if not all_entries:
        raise ValueError("邏輯組合積木未包含有效子條件。")

    if operator == "and":
        combined_entries = all_entries[0]
        for e in all_entries[1:]:
            combined_entries = combined_entries & e
        combined_exits = all_exits[0]
        for e in all_exits[1:]:
            combined_exits = combined_exits | e
    else:  # or
        combined_entries = all_entries[0]
        for e in all_entries[1:]:
            combined_entries = combined_entries | e
        combined_exits = all_exits[0]
        for e in all_exits[1:]:
            combined_exits = combined_exits & e

    return combined_entries, combined_exits, {"operator": operator, "conditions": conditions}


STRATEGY_REGISTRY: Dict[str, StrategyFunction] = {
    "close_above_ma": _strategy_close_above_ma,
    "rsi": _strategy_rsi,
    "macd": _strategy_macd,
    "bollinger_bands": _strategy_bollinger_bands,
    "combine": _strategy_combine,
}


def _build_equity_curve(portfolio: vbt.Portfolio, init_cash: float) -> list[Dict[str, Any]]:
    """生成回測期間每個時間點的累積報酬率序列。"""
    equity_series = portfolio.value()
    cumulative_return = equity_series / init_cash - 1.0
    return [
        {
            "timestamp": ts.isoformat(),
            "cumulative_return": float(cr),
        }
        for ts, cr in zip(cumulative_return.index, cumulative_return)
    ]


def _build_price_series(price_df: pd.DataFrame) -> list[Dict[str, Any]]:
    """生成回測期間的價格時間序列資料。"""
    return [
        {
            "timestamp": ts.isoformat(),
            "close": float(close),
        }
        for ts, close in zip(price_df.index, price_df["close"])
    ]


def _extract_trade_signals(
    price_df: pd.DataFrame, portfolio: vbt.Portfolio
) -> list[Dict[str, Any]]:
    """從 portfolio.trades 中抽取進出場訊號，用於圖表標註。"""
    records = portfolio.trades.records
    if records.empty:
        return []

    signals: list[Dict[str, Any]] = []
    for row in records.itertuples(index=False):
        direction = "long" if int(getattr(row, "direction", 0)) == 0 else "short"
        trade_id = int(getattr(row, "id", -1))
        entry_idx = int(row.entry_idx)
        entry_timestamp = price_df.index[entry_idx].isoformat()
        signals.append(
            {
                "type": "buy",
                "trade_id": trade_id,
                "timestamp": entry_timestamp,
                "price": float(row.entry_price),
                "size": float(getattr(row, "size", 0.0)),
                "direction": direction,
            }
        )

        exit_idx_val = getattr(row, "exit_idx", None)
        if exit_idx_val is not None and pd.notnull(exit_idx_val):
            exit_idx = int(exit_idx_val)
            exit_timestamp = price_df.index[exit_idx].isoformat()
            signals.append(
                {
                    "type": "sell",
                    "trade_id": trade_id,
                    "timestamp": exit_timestamp,
                    "price": float(row.exit_price),
                    "size": float(getattr(row, "size", 0.0)),
                    "direction": direction,
                }
            )

    return sorted(signals, key=lambda item: item["timestamp"])


def fetch_ohlcv(
    symbol: str,
    timeframe: str,
    start_date: str,
    exchange_id: str = "binance",
    limit: int = 1000,
) -> pd.DataFrame:
    """從 ccxt 抓取 OHLCV 歷史資料並回傳 pandas DataFrame。"""
    headers = ["timestamp", "open", "high", "low", "close", "volume"]
    since_ms = _parse_start_date(start_date)
    cache_path = _get_cache_path(symbol, timeframe, exchange_id)

    if _is_cache_valid(cache_path):
        try:
            df = _load_cache(cache_path)
            df = df[df.index >= pd.to_datetime(start_date, utc=True)]
            if not df.empty:
                return df
        except Exception as exc:
            logger.warning("載入緩存失敗，將重新抓取資料: %s", exc)

    try:
        exchange_cls = getattr(ccxt, exchange_id)
        exchange = exchange_cls({"enableRateLimit": True})
    except AttributeError as exc:
        raise ValueError(f"不支援的交易所: {exchange_id}") from exc
    except Exception as exc:
        raise RuntimeError(f"建立交易所連線失敗: {exc}") from exc

    try:
        raw_ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since_ms, limit=limit)
    except ccxt.BaseError as exc:
        logger.exception("CCXT 讀取 OHLCV 失敗")
        raise RuntimeError(
            f"無法從 {exchange_id} 取得 {symbol} 的 OHLCV 歷史資料: {exc}"
        ) from exc

    if not raw_ohlcv:
        raise ValueError(
            f"未取得任何歷史資料，請確認交易對 {symbol}、時間週期 {timeframe} 與起始日期 {start_date} 是否正確。"
        )

    df = pd.DataFrame(raw_ohlcv, columns=headers)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df.set_index("timestamp", inplace=True)

    if df.empty:
        raise ValueError("轉換後的 OHLCV 資料集為空。")

    try:
        _save_cache(df, cache_path)
    except Exception as exc:
        logger.warning("無法寫入緩存: %s", exc)

    return df


def run_backtest(
    symbol: str,
    timeframe: str,
    start_date: str,
    strategy_params: Optional[Dict[str, Any]] = None,
    exchange_id: str = "binance",
    limit: int = 1000,
) -> Dict[str, Any]:
    """執行簡單回測，回傳績效指標與圖表資料。"""
    strategy_params = strategy_params or {}
    strategy_name = strategy_params.get("strategy", "close_above_ma")

    try:
        price_df = fetch_ohlcv(symbol, timeframe, start_date, exchange_id=exchange_id, limit=limit)
    except Exception as exc:
        logger.exception("fetch_ohlcv 發生錯誤")
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "start_date": start_date,
            "strategy": strategy_name,
            "strategy_params": strategy_params,
            "error": str(exc),
            "cumulative_return": None,
            "max_drawdown": None,
            "trade_count": 0,
            "equity_curve": [],
            "signals": [],
            "price_series": [],
        }

    if "close" not in price_df.columns:
        raise ValueError("OHLCV 資料缺少 close 欄位。")

    if strategy_name not in STRATEGY_REGISTRY:
        raise ValueError(
            f"不支援的策略: {strategy_name}。可用策略: {', '.join(STRATEGY_REGISTRY.keys())}"
        )

    strategy_fn = STRATEGY_REGISTRY[strategy_name]

    try:
        entries, exits, used_params = strategy_fn(price_df, strategy_params)
    except NotImplementedError as exc:
        raise
    except Exception as exc:
        logger.exception("策略信號產生失敗")
        raise RuntimeError(f"策略信號產生失敗: {exc}") from exc

    if entries.sum() == 0:
        logger.warning("策略未產生任何買入訊號。")

    initial_cash = 10000.0
    try:
        freq = _convert_timeframe_to_timedelta(timeframe)
        portfolio = vbt.Portfolio.from_signals(
            price_df["close"],
            entries,
            exits,
            freq=freq,
            init_cash=initial_cash,
            fees=0.0,
            slippage=0.0,
        )
    except Exception as exc:
        logger.exception("vectorbt 回測計算失敗")
        raise RuntimeError(f"回測計算失敗: {exc}") from exc

    try:
        cumulative_return = float(portfolio.total_return())
        max_drawdown = float(portfolio.max_drawdown())
        trade_count = int(len(portfolio.trades))
        equity_curve = _build_equity_curve(portfolio, initial_cash)
        signals = _extract_trade_signals(price_df, portfolio)
        price_series = _build_price_series(price_df)

        # Win rate: fraction of trades with positive PnL
        if trade_count > 0:
            trade_records = portfolio.trades.records
            winning = int((trade_records["pnl"] > 0).sum())
            win_rate = winning / trade_count
        else:
            win_rate = 0.0
    except Exception as exc:
        logger.exception("計算績效指標或訊號資料失敗")
        raise RuntimeError(f"計算績效指標或訊號資料失敗: {exc}") from exc

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "start_date": start_date,
        "strategy": strategy_name,
        "strategy_params": used_params,
        "cumulative_return": cumulative_return,
        "win_rate": win_rate,
        "max_drawdown": max_drawdown,
        "trade_count": trade_count,
        "data_points": len(price_df),
        "equity_curve": equity_curve,
        "signals": signals,
        "price_series": price_series,
    }
