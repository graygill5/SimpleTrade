from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .schemas import (
    BuySellRequest,
    MessageResponse,
    PortfolioResponse,
    HistoryResponse,
    StockSnapshotResponse,
    AnalyzeResponse,
)
from .service import (
    get_account,
    portfolio_json,
    history_json,
    buy,
    sell,
    reset,
    stock_snapshot,
    analyze_market_json,
)

app = FastAPI(title="ProfitPlug API", version="1.0")

# Dev CORS so your website can call the API locally
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

acct = get_account("Main")


@app.get("/health", response_model=MessageResponse)
def health():
    return {"ok": True, "message": "ok"}


@app.get("/portfolio", response_model=PortfolioResponse)
def get_portfolio():
    return portfolio_json(acct)


@app.get("/history", response_model=HistoryResponse)
def get_history():
    return history_json(acct)


@app.post("/buy", response_model=MessageResponse)
def post_buy(body: BuySellRequest):
    msg = buy(acct, body.symbol, body.shares)
    return {"ok": True, "message": msg}


@app.post("/sell", response_model=MessageResponse)
def post_sell(body: BuySellRequest):
    msg = sell(acct, body.symbol, body.shares)
    return {"ok": True, "message": msg}


@app.post("/reset", response_model=MessageResponse)
def post_reset():
    msg = reset(acct, starting_cash=1_000_000.0)
    return {"ok": True, "message": msg}


@app.get("/stock/{symbol}", response_model=StockSnapshotResponse)
def get_stock(symbol: str):
    return stock_snapshot(symbol, headlines=5)


@app.get("/analyze", response_model=AnalyzeResponse)
def get_analyze():
    return analyze_market_json()

