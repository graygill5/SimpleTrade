const API_BASE = "http://127.0.0.1:8000";

export type Position = {
  symbol: string;
  shares: number;
  avg_cost: number;
  price?: number | null;
  market_value?: number | null;
  unrealized_pnl?: number | null;
};

export type Portfolio = {
  cash: number;
  equity: number;
  positions: Position[];
};

export type Trade = {
  time: string;
  action: string;
  symbol: string;
  shares: number;
  price: number;
  total: number;
  realized_pnl?: number | null;
};

export type History = { trades: Trade[] };

export type StockSnapshot = {
  symbol: string;
  name?: string | null;
  currency?: string | null;
  price?: number | null;
  day_change_pct?: number | null;
  low_52w?: number | null;
  high_52w?: number | null;
  market_cap?: number | null;
  pe?: number | null;
  eps?: number | null;
  beta?: number | null;
  sector?: string | null;
  rsi14?: number | null;
  sma20?: number | null;
  sma50?: number | null;
  sma200?: number | null;
  headlines: any[];
};

export type Analyze = {
  technicals: Record<string, any>;
  macro_headlines: any[];
  equity_headlines: any[];
  ai_note: string;
};

async function http<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(opts?.headers || {}) },
    ...opts
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => http<{ ok: boolean; message: string }>("/health"),
  portfolio: () => http<Portfolio>("/portfolio"),
  history: () => http<History>("/history"),
  buy: (symbol: string, shares: number) =>
    http<{ ok: boolean; message: string }>("/buy", {
      method: "POST",
      body: JSON.stringify({ symbol, shares })
    }),
  sell: (symbol: string, shares: number) =>
    http<{ ok: boolean; message: string }>("/sell", {
      method: "POST",
      body: JSON.stringify({ symbol, shares })
    }),
  reset: () =>
    http<{ ok: boolean; message: string }>("/reset", { method: "POST" }),
  stock: (symbol: string) => http<StockSnapshot>(`/stock/${encodeURIComponent(symbol)}`),
  analyze: () => http<Analyze>("/analyze")
};

