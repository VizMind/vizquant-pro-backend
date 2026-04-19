import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="VizQuant Backtest API",
    description="後端回測服務，提供加密貨幣策略回測與資料查詢介面",
    version="0.1.0",
)

_raw_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:5173",
)
origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

try:
    from backend.routers.backtest import router as backtest_router
except ImportError:
    from routers.backtest import router as backtest_router

# 後續可在 routers/ 裡新增路由並註冊
app.include_router(backtest_router)

@app.get("/", tags=["health"])
async def root():
    return {"message": "VizQuant Pro Backtest API is running"}
