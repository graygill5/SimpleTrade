import React, { useEffect, useState } from "react";
import Card from "../components/Card.jsx";
import { api } from "../api.js";

export default function History() {
  const [trades, setTrades] = useState([]);

  async function load() {
    const r = await api.listTrades();
    if (r.ok) setTrades(r.trades);
  }
  useEffect(() => { load(); }, []);

  return (
    <Card title="Recent Trades" right={<button className="btn ghost" onClick={load}>Refresh</button>}>
      <table className="table">
        <thead>
          <tr>
            <th>ID</th><th>Order</th><th>Maker</th><th>Taker</th><th>Side</th><th>Size</th><th>Price</th><th>Time</th>
          </tr>
        </thead>
        <tbody>
          {trades.length === 0 ? (
            <tr><td colSpan="8" className="center">No trades yet.</td></tr>
          ) : trades.map(t => (
            <tr key={t.id}>
              <td>{t.id}</td>
              <td>#{t.orderId}</td>
              <td>{t.maker}</td>
              <td>{t.taker}</td>
              <td><span className={`badge ${t.side.toLowerCase()}`}>{t.side}</span></td>
              <td>{t.size.toFixed(4)}</td>
              <td>${t.price.toFixed(4)}</td>
              <td>{new Date(t.ts).toLocaleTimeString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

