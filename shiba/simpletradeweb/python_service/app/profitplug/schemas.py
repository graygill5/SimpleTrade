from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class InitAccountRequest(BaseModel):
    account_name: str = Field(default="Main")
    starting_cash: float = Field(default=1_000_000.0)

class TradeRequest(BaseModel):
    account_id: int
    symbol: str
    shares: int

class ResetRequest(BaseModel):
    account_id: int
    starting_cash: float = Field(default=1_000_000.0)

class AnalyzeRequest(BaseModel):
    tickers: List[str] = Field(default_factory=lambda: ["SPY", "QQQ", "BTC-USD", "AAPL", "MSFT"])

class InfoResponse(BaseModel):
    topic: str
    text: str

class APIResponse(BaseModel):
    ok: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

