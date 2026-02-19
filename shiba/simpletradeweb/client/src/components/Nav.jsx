import React from "react";
import { progressStore } from "../data/lessons.js"; // ← add this import

export default function Nav({ route, setRoute, user, price }) {
  function go(r) { setRoute(r); }
  function logout() {
    localStorage.removeItem("user");
    location.reload();
  }
  const xp = progressStore.getXP(); // ← optional XP read

  return (
    <nav>
      <h1>SimpleTrade</h1>
      <div className="muted">Signed in as <b>{user}</b></div>
      <button onClick={() => go("dashboard")} className={route==="dashboard"?"active":""}>Dashboard</button>
      <button onClick={() => go("trade")} className={route==="trade"?"active":""}>Trade</button>
      <button onClick={() => go("orderbook")} className={route==="orderbook"?"active":""}>Order Book</button>
      <button onClick={() => go("history")} className={route==="history"?"active":""}>History</button>

      {/* New Lessons button */}
      <button onClick={() => go("lessons")} className={route==="lessons"?"active":""}>Lessons</button>

      <div className="price">STUDENT/USD: ${price.toFixed(4)}</div>
      <div className="muted" style={{marginTop:6}}>XP: <b>{xp}</b></div>

      <div style={{marginTop:12}}>
        <button className="btn ghost" onClick={logout}>Log out</button>
      </div>
    </nav>
  );
}

