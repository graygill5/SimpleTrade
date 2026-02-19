import express from "express";
import cors from "cors";

const app = express();
app.use(cors({ origin: "http://localhost:5173", credentials: true }));
app.use(express.json());

/**
 * ===== In-memory state (reset on restart) =====
 * Users: { username: { usd, student, createdAt } }
 * Orders: { id, maker, side: 'BUY'|'SELL', size, price, remaining, createdAt, active }
 * Trades: { id, orderId, maker, taker, side, size, price, ts }
 */
const users = {};
const orders = {};
const trades = [];
let nextOrderId = 1;
let nextTradeId = 1;

// Price engine (random-walk on STUDENT/USD)
let price = 1.00; // start at $1.00
function tickPrice() {
  const drift = 0;
  const vol = 0.01; // 1% step
  const step = (Math.random() - 0.5) * 2 * vol + drift;
  price = Math.max(0.1, +(price * (1 + step)).toFixed(4));
}
setInterval(tickPrice, 1500);

// ===== SSE price stream =====
const sseClients = new Set();
app.get("/api/stream", (req, res) => {
  res.writeHead(200, {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    Connection: "keep-alive",
    "Access-Control-Allow-Origin": "http://localhost:5173"
  });
  res.write(`event: price\n`);
  res.write(`data: ${JSON.stringify({ symbol: "STUDENT/USD", price })}\n\n`);
  const client = { res };
  sseClients.add(client);
  req.on("close", () => sseClients.delete(client));
});
setInterval(() => {
  const payload = `event: price\ndata: ${JSON.stringify({ symbol: "STUDENT/USD", price })}\n\n`;
  for (const c of sseClients) c.res.write(payload);
}, 1500);

// ===== Helpers =====
function ensureUser(username) {
  if (!username || typeof username !== "string") throw new Error("username required");
  if (!users[username]) {
    users[username] = { usd: 1000, student: 100, createdAt: Date.now() };
  }
  return users[username];
}
function getActiveOrders() {
  return Object.values(orders).filter((o) => o.active);
}

// ===== API Routes =====
app.get("/api/health", (_req, res) => res.json({ ok: true, price }));

app.post("/api/register", (req, res) => {
  try {
    const { username } = req.body;
    const u = ensureUser(username);
    res.json({ ok: true, user: { username, ...u } });
  } catch (e) {
    res.status(400).json({ ok: false, error: e.message });
  }
});

app.get("/api/me", (req, res) => {
  try {
    const username = req.query.user;
    const u = ensureUser(username);
    res.json({ ok: true, balances: u });
  } catch (e) {
    res.status(400).json({ ok: false, error: e.message });
  }
});

app.get("/api/prices", (_req, res) => {
  res.json({ ok: true, symbol: "STUDENT/USD", price });
});

app.get("/api/orders", (_req, res) => {
  const list = getActiveOrders().sort((a, b) => b.createdAt - a.createdAt);
  res.json({ ok: true, orders: list });
});

app.get("/api/trades", (_req, res) => {
  res.json({ ok: true, trades: trades.slice(-200).reverse() });
});

// Create order (escrow funds)
app.post("/api/orders", (req, res) => {
  try {
    const { user, side, size, price: p } = req.body;
    if (!["BUY", "SELL"].includes(side)) throw new Error("side must be BUY or SELL");
    const sz = +size, pr = +p;
    if (!(sz > 0 && pr > 0)) throw new Error("size and price must be > 0");
    const u = ensureUser(user);

    if (side === "BUY") {
      const cost = +(sz * pr).toFixed(4);
      if (u.usd < cost) throw new Error("Insufficient USD for escrow");
      u.usd -= cost; // escrow USD
    } else {
      if (u.student < sz) throw new Error("Insufficient STUDENT for escrow");
      u.student -= sz; // escrow STUDENT
    }

    const id = nextOrderId++;
    orders[id] = {
      id,
      maker: user,
      side,
      size: sz,
      price: pr,
      remaining: sz,
      createdAt: Date.now(),
      active: true
    };
    res.json({ ok: true, order: orders[id] });
  } catch (e) {
    res.status(400).json({ ok: false, error: e.message });
  }
});

// Cancel order (refund remaining escrow)
app.delete("/api/orders/:id", (req, res) => {
  try {
    const id = +req.params.id;
    const { user } = req.query;
    const o = orders[id];
    if (!o || !o.active) throw new Error("Order not found");
    if (o.maker !== user) throw new Error("Not your order");

    const u = ensureUser(user);
    if (o.side === "BUY") {
      const refund = +(o.remaining * o.price).toFixed(4);
      u.usd += refund;
    } else {
      u.student += o.remaining;
    }
    o.active = false;
    res.json({ ok: true, cancelled: id });
  } catch (e) {
    res.status(400).json({ ok: false, error: e.message });
  }
});

// Accept order (partial fill allowed)
app.post("/api/orders/:id/accept", (req, res) => {
  try {
    const id = +req.params.id;
    const { user, size } = req.body;
    const taker = ensureUser(user);
    const o = orders[id];
    if (!o || !o.active) throw new Error("Order not found");
    const qty = +size;
    if (!(qty > 0 && qty <= o.remaining)) throw new Error("Invalid size");

    if (o.side === "BUY") {
      // Maker wants to BUY STUDENT; taker sells STUDENT to maker
      if (taker.student < qty) throw new Error("Taker lacks STUDENT");
      const proceed = +(qty * o.price).toFixed(4);
      taker.student -= qty;
      taker.usd += proceed;
      const maker = ensureUser(o.maker);
      maker.student += qty;
    } else {
      // SELL order: maker sells STUDENT; taker buys STUDENT
      const cost = +(qty * o.price).toFixed(4);
      if (taker.usd < cost) throw new Error("Taker lacks USD");
      taker.usd -= cost;
      taker.student += qty;
      const maker = ensureUser(o.maker);
      maker.usd += cost;
    }

    o.remaining -= qty;
    if (o.remaining === 0) o.active = false;

    const trade = {
      id: nextTradeId++,
      orderId: o.id,
      maker: o.maker,
      taker: user,
      side: o.side,
      size: qty,
      price: o.price,
      ts: Date.now()
    };
    trades.push(trade);

    res.json({ ok: true, order: o, trade });
  } catch (e) {
    res.status(400).json({ ok: false, error: e.message });
  }
});

// Optional friendly root page
app.get("/", (_req, res) => {
  res.type("html").send(`
    <h1>SimpleTrade API</h1>
    <p>Your server is running. Try these endpoints:</p>
    <ul>
      <li><a href="/api/health">/api/health</a></li>
      <li><a href="/api/prices">/api/prices</a></li>
      <li><a href="/api/orders">/api/orders</a></li>
      <li><a href="/api/trades">/api/trades</a></li>
      <li><a href="/api/stream">/api/stream</a> (SSE)</li>
    </ul>
    <p>The UI runs separately on <code>http://localhost:5173</code>.</p>
  `);
});

const PORT = process.env.PORT || 4000;
app.listen(PORT, () => {
  console.log(`SimpleTrade server running on http://localhost:${PORT}`);
});

