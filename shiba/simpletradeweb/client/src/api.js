const BASE = "http://localhost:4000/api";

async function call(path, method = "GET", body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(`${BASE}${path}`, opts);
  return r.json();
}

export const api = {
  register: (username) => call("/register", "POST", { username }),
  me: (user) => call(`/me?user=${encodeURIComponent(user)}`),
  prices: () => call("/prices"),
  listOrders: () => call("/orders"),
  listTrades: () => call("/trades"),
  placeOrder: (payload) => call("/orders", "POST", payload),
  cancelOrder: (id, user) => call(`/orders/${id}?user=${encodeURIComponent(user)}`, "DELETE"),
  acceptOrder: (id, payload) => call(`/orders/${id}/accept`, "POST", payload)
};

export function priceStream(onPrice) {
  const es = new EventSource(`${BASE}/stream`);
  es.addEventListener("price", (e) => {
    const data = JSON.parse(e.data);
    onPrice(data);
  });
  return () => es.close();
}

