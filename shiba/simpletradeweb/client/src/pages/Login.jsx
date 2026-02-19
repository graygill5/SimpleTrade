import React, { useState } from "react";
import { api } from "../api.js";

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    const name = username.trim();
    if (!name) return;
    const res = await api.register(name);
    if (res.ok) onLogin(name);
    else alert(res.error || "Login failed");
  }

  return (
    <div style={{display:"grid", placeItems:"center", minHeight:"100vh"}}>
      <div className="card" style={{width:360}}>
        <h2>Welcome to SimpleTrade</h2>
        <p className="muted">Create a username to get started. We’ll give you demo balances.</p>
        <form onSubmit={handleSubmit} style={{display:"grid", gap:12}}>
          <input className="input" placeholder="username" value={username} onChange={e=>setUsername(e.target.value)} />
          <button className="btn" type="submit">Enter</button>
        </form>
      </div>
    </div>
  );
}

