from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

from app.profitplug.db import init_db, list_accounts
from app.profitplug.account import PaperAccount
from app.profitplug.market import show_symbol, analyze_market, ai_take
from app.profitplug.schemas import (
    InitAccountRequest, TradeRequest, ResetRequest, AnalyzeRequest
)

app = FastAPI(title="ProfitPlug API", version="1.0.0")

# Allow your React dev server + Node dev server to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/pp/health")
def health():
    return {"ok": True}

@app.post("/pp/init")
def init_account(req: InitAccountRequest):
    try:
        acc_id = init_db(starting_cash=req.starting_cash, account_name=req.account_name)
        return {"ok": True, "account_id": acc_id}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/pp/accounts")
def accounts():
    return {"ok": True, "accounts": list_accounts()}

@app.get("/pp/portfolio/{account_id}")
def portfolio(account_id: int):
    try:
        acct = PaperAccount(account_id)
        return {"ok": True, "portfolio": acct.portfolio()}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/pp/history/{account_id}")
def history(account_id: int, limit: int = 200):
    try:
        acct = PaperAccount(account_id)
        return {"ok": True, "history": acct.history(limit=limit)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/pp/buy")
def buy(req: TradeRequest):
    try:
        acct = PaperAccount(req.account_id)
        out = acct.buy(req.symbol, req.shares)
        return {"ok": True, "trade": out}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/pp/sell")
def sell(req: TradeRequest):
    try:
        acct = PaperAccount(req.account_id)
        out = acct.sell(req.symbol, req.shares)
        return {"ok": True, "trade": out}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/pp/reset")
def reset(req: ResetRequest):
    try:
        acct = PaperAccount(req.account_id)
        out = acct.reset(starting_cash=req.starting_cash)
        return {"ok": True, "reset": out}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/pp/show/{symbol}")
def show(symbol: str, headlines: int = 5):
    try:
        return {"ok": True, "data": show_symbol(symbol, headlines=headlines)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/pp/analyze")
def analyze(req: AnalyzeRequest):
    try:
        base = analyze_market(req.tickers)
        ai = ai_take(base)
        return {"ok": True, "data": {"market": base, "ai": ai}}
    except Exception as e:
        return {"ok": False, "error": str(e)}

