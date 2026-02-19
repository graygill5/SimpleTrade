import React, { useEffect, useState } from "react";
import Login from "./pages/Login.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Trade from "./pages/Trade.jsx";
import OrderBook from "./pages/OrderBook.jsx";
import History from "./pages/History.jsx";
import Lessons from "./pages/Lessons.jsx"; // ← add this
import Nav from "./components/Nav.jsx";
import { priceStream } from "./api.js";

export default function App() {
  const [user, setUser] = useState(localStorage.getItem("user") || "");
  const [route, setRoute] = useState("dashboard");
  const [price, setPrice] = useState(1.0);

  useEffect(() => {
    const close = priceStream((p) => setPrice(p.price));
    return () => close();
  }, []);

  async function onLogin(username) {
    localStorage.setItem("user", username);
    setUser(username);
  }

  if (!user) return <Login onLogin={onLogin} />;

  return (
    <div className="container">
      <Nav route={route} setRoute={setRoute} user={user} price={price} />
      <main>
        {route === "dashboard" && <Dashboard user={user} price={price} />}
        {route === "trade" && <Trade user={user} price={price} />}
        {route === "orderbook" && <OrderBook user={user} />}
        {route === "history" && <History />}
        {route === "lessons" && <Lessons />}  {/* ← new route */}
      </main>
    </div>
  );
}

