import React, { useEffect, useState } from "react";
import Card from "../components/Card.jsx";
import { api } from "../api.js";

export default function OrderBook({ user }) {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [acceptQty, setAcceptQty] = useState({}); // orderId -> qty

  async function load() {
    setLoading(true);
    const r = await api.listOrders();
    setLoading(false);
    if (r.ok) setOrders(r.orders);
  }
  useEffect(() => { load(); }, []);

  async function cancel(id) {
    const r = await api.cancelOrder(id, user);
    if (!r.ok) return alert(r.error);
    await load();
  }

  async function accept(id) {
    const qty = Number(acceptQty[id] || 0);
    if (!(qty > 0)) return alert("Enter a valid size");
    const r = await api.acceptOrder(id, { user, size: qty });
    if (!r.ok) return alert(r.error);
    setAcceptQty({ ...acceptQty, [id]: "" });
    await load();
  }

  return (
    <div>
      <Card title="Order Book" right={<button className="btn ghost" onClick={load}>Refresh</button>}>
        <table className="table">
          <thead>
            <tr>
              <th>ID</th><th>Maker</th><th>Side</th><th>Price</th><th>Remaining</th><th>Action</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan="6" className="center">Loading…</td></tr>
            ) : orders.length === 0 ? (
              <tr><td colSpan="6" className="center">No active orders.</td></tr>
            ) : orders.map(o => (
              <tr key={o.id}>
                <td>{o.id}</td>
                <td>{o.maker}</td>
                <td><span className={`badge ${o.side.toLowerCase()}`}>{o.side}</span></td>
                <td>${o.price.toFixed(4)}</td>
                <td>{o.remaining.toFixed(4)}</td>
                <td>
                  {o.maker === user ? (
                    <button className="btn ghost" onClick={() => cancel(o.id)}>Cancel</button>
                  ) : (
                    <div style={{display:"flex", gap:6}}>
                      <input
                        className="input"
                        style={{width:120}}
                        placeholder="size"
                        value={acceptQty[o.id] || ""}
                        onChange={e=>setAcceptQty({...acceptQty, [o.id]: e.target.value})}
                      />
                      <button className="btn" onClick={() => accept(o.id)}>Accept</button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

