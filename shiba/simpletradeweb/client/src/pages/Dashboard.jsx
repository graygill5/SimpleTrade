import React, { useEffect, useState } from "react";
import Card from "../components/Card.jsx";
import { api } from "../api.js";

export default function Dashboard({ user, price }) {
  const [bal, setBal] = useState({ usd: 0, student: 0 });

  async function load() {
    const r = await api.me(user);
    if (r.ok) setBal(r.balances);
  }
  useEffect(() => { load(); }, []);

  const value = bal.usd + bal.student * price;

  return (
    <div>
      <Card title="Balances">
        <div className="row">
          <div>
            <div className="muted">USD</div>
            <h2 style={{margin:"6px 0"}}>${bal.usd?.toFixed?.(4) ?? "0.0000"}</h2>
          </div>
          <div>
            <div className="muted">STUDENT</div>
            <h2 style={{margin:"6px 0"}}>{bal.student?.toFixed?.(4) ?? "0.0000"}</h2>
          </div>
          <div>
            <div className="muted">Portfolio Value</div>
            <h2 style={{margin:"6px 0"}}>${value.toFixed(4)}</h2>
          </div>
        </div>
      </Card>

      <Card title="Quick Actions">
        <div className="row">
          <button className="btn" onClick={load}>Refresh Balances</button>
          <a className="btn ghost" href="#" onClick={(e)=>{e.preventDefault(); alert("Lessons TBD – add later!")}}>Open Lessons (TBD)</a>
        </div>
      </Card>
    </div>
  );
}

