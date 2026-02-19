from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class BuySellRequest(BaseModel):
    symbol: str = Field(..., examples=["AAPL"])
    shares: int = Field(..., gt=0, examples=[5])


class MessageResponse(BaseModel):
    ok: bool
    message: str


class Position(BaseModel):
    symbol: str
    shares: int
    avg_cost: float
    price: Optional[float] = None
    market_value: Optional[float] = None
    unrealized_pnl: Optional[float] = None


class PortfolioResponse(BaseModel):
    cash: float
    equity: float
    positions: List[Position]


class Trade(BaseModel):
    time: str
    action: str
    symbol: str
    shares: int
    price: float
    total: float
    realized_pnl: Optional[float] = None


class HistoryResponse(BaseModel):
    trades: List[Trade]


class StockSnapshotResponse(BaseModel):
    symbol: str
    name: Optional[str] = None
    currency: Optional[str] = None
    price: Optional[float] = None
    day_change_pct: Optional[float] = None
    low_52w: Optional[float] = None
    high_52w: Optional[float] = None

    market_cap: Optional[float] = None
    pe: Optional[float] = None
    eps: Optional[float] = None
    beta: Optional[float] = None
    sector: Optional[str] = None

    rsi14: Optional[float] = None
    sma20: Optional[float] = None
    sma50: Optional[float] = None
    sma200: Optional[float] = None

    headlines: List[Dict[str, Any]] = []


class AnalyzeResponse(BaseModel):
    technicals: Dict[str, Any]
    macro_headlines: List[Dict[str, Any]]
    equity_headlines: List[Dict[str, Any]]
    ai_note: str

