// SimpleTrade educational modules (client-side only)
export const lessons = [
  {
    id: "intro-trading",
    title: "Trading 101: Orders, Price, and P/L",
    minutes: 5,
    content: [
      "An order is an instruction to buy or sell an asset.",
      "A LIMIT order sets the maximum (buy) or minimum (sell) price you’re willing to accept.",
      "Your Profit/Loss (P/L) = (Sell Price − Buy Price) × Quantity, minus fees.",
      "A spread is the gap between best bid (highest buyer) and best ask (lowest seller)."
    ],
    quiz: {
      question: "Which statement about LIMIT orders is true?",
      choices: [
        "A LIMIT buy will execute at any price available.",
        "A LIMIT sell only executes at or above your limit price.",
        "LIMIT orders always execute immediately.",
        "LIMIT orders are illegal on Wednesdays (joking!)."
      ],
      correctIndex: 1,
      explain: "A sell limit sets a minimum acceptable price. It will not execute below that price."
    },
    rewardXP: 50
  },
  {
    id: "escrow-and-matching",
    title: "Escrow, Matching & Settlement",
    minutes: 6,
    content: [
      "Escrow temporarily holds funds so both sides can safely complete a trade.",
      "Matching pairs a taker with a maker’s standing order at the maker’s price.",
      "Settlement transfers assets: the buyer gets the base asset; the seller gets quote currency.",
      "Partial fills reduce the remaining size of an order; when it reaches zero, the order closes."
    ],
    quiz: {
      question: "Why is escrow used in trading systems like SimpleTrade?",
      choices: [
        "To increase price volatility.",
        "To hold funds so neither side can back out after matching.",
        "To make orders look cooler in the UI.",
        "To reduce the spread automatically."
      ],
      correctIndex: 1,
      explain: "Escrow ensures locked funds are available, enabling safe settlement after a match."
    },
    rewardXP: 50
  },
  {
    id: "risk-basics",
    title: "Risk Basics: Position Sizing & Drawdowns",
    minutes: 7,
    content: [
      "Position sizing is choosing how large a trade should be relative to your balance.",
      "A drawdown is the drop from a peak account value to a subsequent low.",
      "Small, consistent position sizes help avoid large drawdowns.",
      "Use stop-losses or exit rules (even in simulators) to practice discipline."
    ],
    quiz: {
      question: "What helps reduce the impact of losing streaks the most?",
      choices: [
        "Max position every trade.",
        "Randomly change size each time.",
        "Consistent small position sizes.",
        "Ignore your balance and always buy 100."
      ],
      correctIndex: 2,
      explain: "Consistent, smaller sizes help smooth volatility and reduce large drawdowns."
    },
    rewardXP: 75
  }
];

// Simple helper to manage XP/progress in localStorage
export const progressStore = {
  _key: "simpletrade_lessons_progress",
  _xpKey: "simpletrade_xp",
  getProgress() {
    try { return JSON.parse(localStorage.getItem(this._key) || "{}"); }
    catch { return {}; }
  },
  setCompleted(id) {
    const p = this.getProgress();
    p[id] = true;
    localStorage.setItem(this._key, JSON.stringify(p));
  },
  isCompleted(id) {
    const p = this.getProgress();
    return !!p[id];
  },
  getXP() {
    return Number(localStorage.getItem(this._xpKey) || 0);
  },
  addXP(amount) {
    const cur = this.getXP();
    localStorage.setItem(this._xpKey, String(cur + amount));
  }
};

