import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()  # Load .env for local development
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
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

try:
    from backend.routers.backtest import router as backtest_router
    from backend.routers.strategy import router as strategy_router
    from backend.routers.user import router as user_router
    from backend.routers.webhook import router as webhook_router
except ImportError:
    from routers.backtest import router as backtest_router
    from routers.strategy import router as strategy_router
    from routers.user import router as user_router
    from routers.webhook import router as webhook_router

app.include_router(backtest_router)
app.include_router(user_router)
app.include_router(strategy_router)
app.include_router(webhook_router)

@app.get("/", tags=["health"])
async def root():
    return {"message": "VizQuant Pro Backtest API is running"}
