import React, { useEffect, useMemo, useState } from "react";
import { api, Analyze, History, Portfolio, StockSnapshot } from "./api";

function money(x?: number | null) {
  if (x === null || x === undefined || Number.isNaN(x)) return "-";
  return x.toLocaleString(undefined, { style: "currency", currency: "USD" });
}

function num(x?: number | null) {
  if (x === null || x === undefined || Number.isNaN(x)) return "-";
  return x.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export default function App() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [history, setHistory] = useState<History | null>(null);

  const [symbol, setSymbol] = useState("AAPL");
  const [shares, setShares] = useState(1);
  const [action, setAction] = useState<"buy" | "sell">("buy");

  const [stockSymbol, setStockSymbol] = useState("AAPL");
  const [stock, setStock] = useState<StockSnapshot | null>(null);

  const [analyze, setAnalyze] = useState<Analyze | null>(null);

  const [msg, setMsg] = useState<string>("");
  const [loading, setLoading] = useState(false);

  async function refresh() {
    const [p, h] = await Promise.all([api.portfolio(), api.history()]);
    setPortfolio(p);
    setHistory(h);
  }

  useEffect(() => {
    refresh().catch((e) => setMsg(String(e.message || e)));
  }, []);

  const positionsSorted = useMemo(() => {
    if (!portfolio) return [];
    return [...portfolio.positions].sort((a, b) => a.symbol.localeCompare(b.symbol));
  }, [portfolio]);

  async function doTrade() {
    setLoading(true);
    setMsg("");
    try {
      const sym = symbol.trim().toUpperCase();
      if (!sym) throw new Error("Symbol is required");
      if (shares <= 0) throw new Error("Shares must be > 0");

      const res =
        action === "buy"
          ? await api.buy(sym, shares)
          : await api.sell(sym, shares);

      setMsg(res.message);
      await refresh();
    } catch (e: any) {
      setMsg(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function loadStock() {
    setLoading(true);
    setMsg("");
    try {
      const sym = stockSymbol.trim().toUpperCase();
      const snap = await api.stock(sym);
      setStock(snap);
    } catch (e: any) {
      setMsg(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function loadAnalyze() {
    setLoading(true);
    setMsg("");
    try {
      const a = await api.analyze();
      setAnalyze(a);
    } catch (e: any) {
      setMsg(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function doReset() {
    setLoading(true);
    setMsg("");
    try {
      const res = await api.reset();
      setMsg(res.message);
      await refresh();
    } catch (e: any) {
      setMsg(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="container">
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 14 }}>
        <h1>ProfitPlug</h1>
        <span className="pill">local dev</span>
        <span className="small" style={{ marginLeft: "auto" }}>
          API: http://127.0.0.1:8000
        </span>
      </div>

      {msg ? (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="small">{msg}</div>
        </div>
      ) : null}

      <div className="row" style={{ marginBottom: 16 }}>
        <div className="card">
          <h2>Account</h2>
          <div className="small" style={{ marginBottom: 10 }}>
            Paper trading portfolio. Buy/sell updates the sqlite DB.
          </div>

          <div style={{ display: "flex", gap: 10, marginBottom: 10 }}>
            <div style={{ flex: 1 }}>
              <div className="small">Symbol</div>
              <input className="input" value={symbol} onChange={(e) => setSymbol(e.target.value)} />
            </div>
            <div style={{ width: 140 }}>
              <div className="small">Shares</div>
              <input
                className="input"
                type="number"
                value={shares}
                onChange={(e) => setShares(parseInt(e.target.value || "0", 10))}
              />
            </div>
          </div>

          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <select
              className="input"
              style={{ width: 140 }}
              value={action}
              onChange={(e) => setAction(e.target.value as any)}
            >
              <option value="buy">BUY</option>
              <option value="sell">SELL</option>
            </select>

            <button className="btn" onClick={doTrade} disabled={loading}>
              {loading ? "Working..." : "Submit"}
            </button>

            <button className="btn" onClick={doReset} disabled={loading} style={{ marginLeft: "auto", background: "#ff5c5c" }}>
              Reset
            </button>
          </div>

          <div style={{ display: "flex", gap: 16, marginTop: 14 }}>
            <div>
              <div className="small">Cash</div>
              <div style={{ fontSize: "1.2rem", fontWeight: 700 }}>
                {portfolio ? money(portfolio.cash) : "-"}
              </div>
            </div>
            <div>
              <div className="small">Equity</div>
              <div style={{ fontSize: "1.2rem", fontWeight: 700 }}>
                {portfolio ? money(portfolio.equity) : "-"}
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <h2>Portfolio</h2>
          <div className="small" style={{ marginBottom: 10 }}>
            Live prices from Yahoo Finance. Unrealized P/L is approximate.
          </div>

          <table className="table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Shares</th>
                <th>Avg</th>
                <th>Price</th>
                <th>Mkt Value</th>
                <th>Unreal P/L</th>
              </tr>
            </thead>
            <tbody>
              {positionsSorted.length === 0 ? (
                <tr>
                  <td colSpan={6} className="small">(no positions)</td>
                </tr>
              ) : (
                positionsSorted.map((p) => {
                  const pnl = p.unrealized_pnl ?? null;
                  const cls = pnl === null ? "" : pnl >= 0 ? "green" : "red";
                  return (
                    <tr key={p.symbol}>
                      <td>{p.symbol}</td>
                      <td>{p.shares}</td>
                      <td>{money(p.avg_cost)}</td>
                      <td>{money(p.price ?? null)}</td>
                      <td>{money(p.market_value ?? null)}</td>
                      <td className={cls}>{money(pnl)}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="row" style={{ marginBottom: 16 }}>
        <div className="card">
          <h2>Stock Snapshot</h2>
          <div style={{ display: "flex", gap: 10, marginBottom: 10 }}>
            <input className="input" value={stockSymbol} onChange={(e) => setStockSymbol(e.target.value)} />
            <button className="btn" onClick={loadStock} disabled={loading}>
              Load
            </button>
          </div>

          {!stock ? (
            <div className="small">(load a symbol)</div>
          ) : (
            <>
              <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
                <h3>{stock.name || stock.symbol}</h3>
                <span className="pill">{stock.symbol}</span>
              </div>

              <div style={{ display: "flex", gap: 16, marginTop: 10 }}>
                <div>
                  <div className="small">Price</div>
                  <div style={{ fontSize: "1.2rem", fontWeight: 700 }}>
                    {stock.price != null ? `${stock.currency || "USD"} ${num(stock.price)}` : "-"}
                  </div>
                  <div className="small">
                    Day: {stock.day_change_pct != null ? `${num(stock.day_change_pct)}%` : "-"}
                  </div>
                </div>

                <div>
                  <div className="small">52w</div>
                  <div className="small">
                    Low {num(stock.low_52w)} / High {num(stock.high_52w)}
                  </div>
                  <div className="small">
                    RSI {num(stock.rsi14)} | SMA50 {num(stock.sma50)}
                  </div>
                </div>
              </div>

              <div style={{ marginTop: 12 }}>
                <div className="small">Headlines</div>
                {stock.headlines?.length ? (
                  <div className="small" style={{ marginTop: 6 }}>
                    {stock.headlines.slice(0, 5).map((h: any, i: number) => (
                      <div key={i} style={{ marginBottom: 8 }}>
                        • {h.title}{" "}
                        <span style={{ opacity: 0.75 }}>
                          {h.publisher ? `— ${h.publisher}` : ""} {h.time ? `(${h.time})` : ""}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="small">(no headlines)</div>
                )}
              </div>
            </>
          )}
        </div>

        <div className="card">
          <h2>Market Analyze</h2>
          <div className="small" style={{ marginBottom: 10 }}>
            Pulls technicals + macro headlines + AI note (if OPENAI_API_KEY set).
          </div>

          <button className="btn" onClick={loadAnalyze} disabled={loading}>
            {loading ? "Working..." : "Run Analyze"}
          </button>

          {!analyze ? (
            <div className="small" style={{ marginTop: 10 }}>(not loaded)</div>
          ) : (
            <div style={{ marginTop: 12 }}>
              <div className="small">AI Note</div>
              <div className="card" style={{ marginTop: 8, background: "#0b0f14" }}>
                <div className="small" style={{ whiteSpace: "pre-wrap" }}>
                  {analyze.ai_note}
                </div>
              </div>

              <div className="small" style={{ marginTop: 12 }}>Technicals</div>
              <div className="small" style={{ marginTop: 6 }}>
                {Object.entries(analyze.technicals).map(([k, v]: any) => (
                  <div key={k} style={{ marginBottom: 6 }}>
                    <span className="pill">{k}</span>{" "}
                    Px {v.price} | {v.trend} | 20/50 {v.cross} | RSI {v.rsi ?? "-"}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <h2>Trade History</h2>
        <div className="small" style={{ marginBottom: 10 }}>
          Stored in sqlite. This is what you’ll graph later.
        </div>

        <table className="table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Action</th>
              <th>Symbol</th>
              <th>Shares</th>
              <th>Price</th>
              <th>Total</th>
              <th>Realized</th>
            </tr>
          </thead>
          <tbody>
            {!history || history.trades.length === 0 ? (
              <tr>
                <td colSpan={7} className="small">(no trades)</td>
              </tr>
            ) : (
              [...history.trades].reverse().slice(0, 25).map((t, idx) => {
                const pnl = t.realized_pnl ?? null;
                const cls = pnl === null ? "" : pnl >= 0 ? "green" : "red";
                return (
                  <tr key={idx}>
                    <td className="small">{t.time}</td>
                    <td>{t.action}</td>
                    <td>{t.symbol}</td>
                    <td>{t.shares}</td>
                    <td>{money(t.price)}</td>
                    <td>{money(t.total)}</td>
                    <td className={cls}>{money(pnl)}</td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

