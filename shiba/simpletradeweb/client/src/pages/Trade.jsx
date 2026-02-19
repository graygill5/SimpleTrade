import React, { useState } from "react";
import Card from "../components/Card.jsx";
import { api } from "../api.js";

export default function Trade({ user, price }) {
  const [side, setSide] = useState("BUY");
  const [size, setSize] = useState("");
  const [limit, setLimit] = useState("");

  async function submit() {
    const r = await api.placeOrder({
      user,
      side,
      size: Number(size),
      price: Number(limit || price)
    });
    if (!r.ok) alert(r.error);
    else {
      alert(`Order #${r.order.id} placed!`);
      setSize("");
      setLimit("");
    }
  }

  return (
    <div className="row">
      <Card title="Place Order">
        <div className="row">
          <div>
            <label className="muted">Side</label>
            <select className="select" value={side} onChange={e=>setSide(e.target.value)}>
              <option>BUY</option>
              <option>SELL</option>
            </select>
          </div>
          <div>
            <label className="muted">Size (STUDENT)</label>
            <input className="input" value={size} onChange={e=>setSize(e.target.value)} placeholder="e.g., 10" />
          </div>
          <div>
            <label className="muted">Limit Price (USD)</label>
            <input className="input" value={limit} onChange={e=>setLimit(e.target.value)} placeholder={`default ${price.toFixed(4)}`} />
          </div>
        </div>
        <div style={{marginTop:12}}>
          <button className="btn" onClick={submit}>Submit Order</button>
        </div>
      </Card>

      <Card title="Ticker">
        <h2 style={{margin:"6px 0"}}>STUDENT/USD</h2>
        <div className="muted">Live (SSE):</div>
        <h1 style={{margin:"6px 0"}}>${price.toFixed(4)}</h1>
      </Card>
    </div>
  );
}

