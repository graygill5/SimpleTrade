(function () {
    var root = document.getElementById("portfolio-app");
    if (!root) return;

    var owner = root.getAttribute("data-owner") || "";
    var readOnly = root.getAttribute("data-read-only") === "1";

    var equityChart = null;
    var allocChart = null;
    var holdingCharts = {};
    var allSnapshots = [];
    var activeEquityRange = "1m";

    function fmtMoney(n) {
        if (n == null || isNaN(n)) return "—";
        var sign = n < 0 ? "-" : "";
        return sign + "$" + Math.abs(n).toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    function fmtNum(n, d) {
        if (n == null || isNaN(n)) return "—";
        return Number(n).toLocaleString(undefined, {
            minimumFractionDigits: d,
            maximumFractionDigits: d,
        });
    }

    function stateUrl() {
        if (readOnly) {
            return "/api/paper/state/" + encodeURIComponent(owner);
        }
        return "/api/paper/state";
    }

    function txUrl() {
        if (readOnly) {
            return "/api/paper/transactions/" + encodeURIComponent(owner);
        }
        return "/api/paper/transactions";
    }

    function getJSON(url) {
        return fetch(url, { credentials: "same-origin" }).then(function (r) {
            if (r.status === 401) {
                window.location.href = "/";
                return Promise.reject(new Error("auth"));
            }
            return r.json().then(function (d) {
                return { ok: r.ok, d: d };
            });
        });
    }

    function renderSummary(p) {
        document.getElementById("pv-cash").textContent = fmtMoney(p.cash);
        document.getElementById("pv-invested").textContent = fmtMoney(p.cost_basis);
        document.getElementById("pv-total").textContent = fmtMoney(p.holdings_market_value);
        var pl = document.getElementById("pv-pl");
        var invested = Number(p.cost_basis || 0);
        var current = Number(p.holdings_market_value || 0);
        var pnl = current - invested;
        var pnlPct = invested > 0 ? (pnl / invested) * 100 : 0;
        var t = fmtMoney(pnl) + " (" + fmtNum(pnlPct, 2) + "% vs invested)";
        pl.textContent = t;
        pl.className = "v " + (pnl >= 0 ? "up" : "down");
    }

    function parseSnapshotTime(s) {
        if (!s) return null;
        var iso = String(s).replace(" ", "T");
        var d = new Date(iso);
        if (isNaN(d.getTime())) return null;
        return d;
    }

    function filterSnapshotsByRange(snapshots, rangeKey) {
        var rows = snapshots || [];
        if (!rows.length || rangeKey === "all") return rows;
        var now = new Date();
        var ms = 0;
        if (rangeKey === "1d") ms = 24 * 60 * 60 * 1000;
        else if (rangeKey === "1w") ms = 7 * 24 * 60 * 60 * 1000;
        else if (rangeKey === "1m") ms = 30 * 24 * 60 * 60 * 1000;
        else if (rangeKey === "3m") ms = 90 * 24 * 60 * 60 * 1000;
        else if (rangeKey === "1y") ms = 365 * 24 * 60 * 60 * 1000;
        if (!ms) return rows;
        var cutoff = now.getTime() - ms;
        var out = rows.filter(function (r) {
            var d = parseSnapshotTime(r.t);
            return d && d.getTime() >= cutoff;
        });
        // Keep at least two points if available.
        if (out.length >= 2) return out;
        return rows.slice(Math.max(0, rows.length - 2));
    }

    function trimToInvestmentStart(snapshots) {
        var rows = snapshots || [];
        if (!rows.length) return rows;
        var startIdx = -1;
        for (var i = 0; i < rows.length; i++) {
            var inv = Number(rows[i].invested || 0);
            if (!isNaN(inv) && inv > 0) {
                startIdx = i;
                break;
            }
        }
        if (startIdx <= 0) return rows;
        return rows.slice(startIdx);
    }

    function renderEquityChart(snapshots) {
        var canvas = document.getElementById("paper-equity-chart");
        var empty = document.getElementById("paper-equity-empty");
        if (!canvas || typeof Chart === "undefined") return;

        var scoped = filterSnapshotsByRange(snapshots, activeEquityRange);

        var labels = [];
        var vals = [];
        scoped.forEach(function (s) {
            labels.push(s.t || "");
            vals.push(Number(s.invested || 0));
        });

        if (vals.length === 0) {
            if (empty) empty.hidden = false;
            if (equityChart) {
                equityChart.destroy();
                equityChart = null;
            }
            return;
        }
        if (empty) empty.hidden = true;

        var up = vals.length >= 2 ? vals[vals.length - 1] >= vals[0] : true;
        var lineColor = up ? "#34d399" : "#f87171";
        var fillColor = up ? "rgba(52, 211, 153, 0.12)" : "rgba(248, 113, 113, 0.12)";

        if (equityChart) equityChart.destroy();
        equityChart = new Chart(canvas.getContext("2d"), {
            type: "line",
            data: {
                labels: labels,
                datasets: [
                    {
                        label: "Invested portfolio value",
                        data: vals,
                        borderColor: lineColor,
                        backgroundColor: fillColor,
                        fill: true,
                        tension: 0.2,
                        pointRadius: 0,
                        borderWidth: 2,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: {
                        ticks: { color: "#64748b", maxTicksLimit: 8 },
                        grid: { color: "rgba(148,163,184,0.08)" },
                    },
                    y: {
                        ticks: {
                            color: "#64748b",
                            callback: function (v) {
                                return "$" + v;
                            },
                        },
                        grid: { color: "rgba(148,163,184,0.08)" },
                    },
                },
            },
        });
    }

    function bindEquityTabs() {
        var tabs = document.getElementById("paper-equity-tabs");
        if (!tabs) return;
        tabs.querySelectorAll(".chart-tab").forEach(function (btn) {
            btn.addEventListener("click", function () {
                var next = btn.getAttribute("data-range") || "1m";
                activeEquityRange = next;
                tabs.querySelectorAll(".chart-tab").forEach(function (b) {
                    b.classList.remove("active");
                });
                btn.classList.add("active");
                renderEquityChart(allSnapshots);
            });
        });
    }

    function renderAllocChart(p) {
        var canvas = document.getElementById("paper-alloc-chart");
        var empty = document.getElementById("paper-alloc-empty");
        if (!canvas || typeof Chart === "undefined") return;

        var pos = p.positions || [];
        var labels = [];
        var data = [];
        var cash = p.cash || 0;
        if (cash > 0.01) {
            labels.push("Cash");
            data.push(cash);
        }
        pos.forEach(function (x) {
            labels.push(x.symbol);
            data.push(x.market_value || 0);
        });

        if (labels.length === 0) {
            if (empty) empty.hidden = false;
            if (allocChart) {
                allocChart.destroy();
                allocChart = null;
            }
            return;
        }
        if (empty) empty.hidden = true;

        var colors = [
            "#38bdf8",
            "#34d399",
            "#fbbf24",
            "#f472b6",
            "#a78bfa",
            "#fb923c",
            "#94a3b8",
        ];
        var bg = labels.map(function (_, i) {
            return colors[i % colors.length] + "cc";
        });

        if (allocChart) allocChart.destroy();
        allocChart = new Chart(canvas.getContext("2d"), {
            type: "doughnut",
            data: {
                labels: labels,
                datasets: [
                    {
                        data: data,
                        backgroundColor: bg,
                        borderWidth: 0,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "right",
                        labels: { color: "#94a3b8", boxWidth: 12 },
                    },
                },
            },
        });
    }

    function renderHoldings(positions) {
        Object.keys(holdingCharts).forEach(function (k) {
            try {
                holdingCharts[k].destroy();
            } catch (e) {}
            delete holdingCharts[k];
        });
        var tb = document.getElementById("paper-holdings-body");
        if (!tb) return;
        tb.innerHTML = "";
        if (!positions || !positions.length) {
            var tr = document.createElement("tr");
            tr.innerHTML =
                '<td colspan="8" class="empty">No positions yet — buy shares with your paper cash.</td>';
            tb.appendChild(tr);
            return;
        }
        positions.forEach(function (x) {
            var tr = document.createElement("tr");
            var upl = x.unrealized_pl;
            var upc = upl >= 0 ? "up" : "down";
            tr.innerHTML =
                "<td class=\"sym\">" +
                escapeHtml(x.symbol) +
                "</td><td>" +
                escapeHtml(x.name || "") +
                "</td><td class=\"rm num\">" +
                fmtNum(x.shares, 4) +
                "</td><td class=\"rm num\">" +
                fmtMoney(x.avg_cost) +
                "</td><td class=\"rm num\">" +
                fmtMoney(x.last) +
                "</td><td class=\"rm num\">" +
                fmtMoney(x.market_value) +
                '</td><td class="rm num ' +
                upc +
                '">' +
                fmtMoney(upl) +
                " (" +
                fmtNum(x.unrealized_pct, 2) +
                "%)</td>" +
                '<td class="rm paper-mini-chart"><canvas class="paper-spark" data-symbol="' +
                escapeHtml(x.symbol) +
                '"></canvas></td>';
            tb.appendChild(tr);
        });
        loadSparklines();
    }

    function escapeHtml(s) {
        var d = document.createElement("div");
        d.textContent = s;
        return d.innerHTML;
    }

    function loadSparklines() {
        var canvases = Array.prototype.slice.call(
            document.querySelectorAll("canvas.paper-spark")
        );
        // Limit sparkline pulls to reduce Yahoo burst traffic.
        canvases.slice(0, 2).forEach(function (cv) {
            var sym = cv.getAttribute("data-symbol");
            if (!sym || holdingCharts[sym]) return;
            fetch("/api/chart/" + encodeURIComponent(sym) + "?range=1m", {
                credentials: "same-origin",
            })
                .then(function (r) {
                    if (!r.ok) return null;
                    return r.json();
                })
                .then(function (d) {
                    if (!d || !d.labels || !d.closes || !d.closes.length) return;
                    holdingCharts[sym] = new Chart(cv.getContext("2d"), {
                        type: "line",
                        data: {
                            labels: d.labels,
                            datasets: [
                                {
                                    data: d.closes,
                                    borderColor: "#64748b",
                                    backgroundColor: "transparent",
                                    borderWidth: 1.2,
                                    pointRadius: 0,
                                    tension: 0.15,
                                },
                            ],
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: { legend: { display: false } },
                            scales: { x: { display: false }, y: { display: false } },
                        },
                    });
                })
                .catch(function () {});
        });
    }

    function renderTx(rows) {
        var tb = document.getElementById("paper-tx-body");
        if (!tb) return;
        tb.innerHTML = "";
        if (!rows || !rows.length) {
            var tr = document.createElement("tr");
            tr.innerHTML =
                '<td colspan="8" class="empty">No transactions yet.</td>';
            tb.appendChild(tr);
            return;
        }
        rows.forEach(function (t) {
            var tr = document.createElement("tr");
            tr.innerHTML =
                "<td>" +
                escapeHtml(t.created_at || "") +
                "</td><td>" +
                escapeHtml(t.kind || "") +
                "</td><td>" +
                escapeHtml(t.symbol || "—") +
                "</td><td class=\"rm\">" +
                (t.shares != null ? fmtNum(t.shares, 4) : "—") +
                "</td><td class=\"rm\">" +
                (t.price != null ? fmtMoney(t.price) : "—") +
                "</td><td class=\"rm\">" +
                fmtMoney(t.amount) +
                "</td><td class=\"rm\">" +
                fmtMoney(t.cash_after) +
                "</td><td class=\"tx-note\">" +
                escapeHtml(t.note || "") +
                "</td>";
            tb.appendChild(tr);
        });
    }

    function renderLeaderboard(items) {
        var ol = document.getElementById("paper-leaderboard");
        if (!ol) return;
        ol.innerHTML = "";
        if (!items || !items.length) {
            ol.innerHTML = "<li class=\"empty\">No data.</li>";
            return;
        }
        items.forEach(function (r) {
            var li = document.createElement("li");
            li.innerHTML =
                "<span class=\"lb-rank\">#" +
                r.rank +
                "</span> <strong>" +
                escapeHtml(r.username) +
                "</strong> — " +
                fmtMoney(r.total_value);
            if (r.username === owner) {
                li.classList.add("lb-me");
            }
            ol.appendChild(li);
        });
    }

    function loadAll() {
        getJSON(stateUrl()).then(function (res) {
            if (!res.ok) {
                document.getElementById("paper-holdings-body").innerHTML =
                    '<tr><td colspan="8" class="empty">' +
                    (res.d.error || "Could not load") +
                    "</td></tr>";
                return;
            }
            var d = res.d;
            var p = d.portfolio;
            if (!p) {
                document.getElementById("paper-holdings-body").innerHTML =
                    '<tr><td colspan="8" class="empty">Portfolio data unavailable. Refresh and try again.</td></tr>';
                return;
            }
            allSnapshots = trimToInvestmentStart(d.snapshots || []);
            renderSummary(p);
            renderEquityChart(allSnapshots);
            renderAllocChart(p);
            renderHoldings(p.positions);
        });

        getJSON(txUrl()).then(function (res) {
            if (res.ok && res.d.transactions) {
                renderTx(res.d.transactions);
            }
        });

        /* Leaderboard recomputes many Yahoo quotes server-side — load after holdings paint. */
        window.setTimeout(function () {
            getJSON("/api/paper/leaderboard").then(function (res) {
                if (res.ok && res.d.leaderboard) {
                    renderLeaderboard(res.d.leaderboard);
                }
            });
        }, 0);
    }

    /* ---- Trade UI (owner only) ---- */
    var searchIn = document.getElementById("paper-symbol-search");
    var searchDd = document.getElementById("paper-search-dd");
    var sharesIn = document.getElementById("paper-shares");
    var quoteEl = document.getElementById("paper-quote-preview");
    var selectedSymbol = null;
    var searchTimer = null;

    function closeDd() {
        if (searchDd) {
            searchDd.classList.remove("open");
            searchDd.innerHTML = "";
        }
    }

    function showQuote(sym) {
        selectedSymbol = sym;
        if (!quoteEl) return;
        quoteEl.textContent = "Loading…";
        getJSON("/api/quote/" + encodeURIComponent(sym)).then(function (res) {
            if (!res.ok || !res.d || res.d.error) {
                quoteEl.textContent = "—";
                return;
            }
            var q = res.d;
            quoteEl.textContent =
                q.symbol +
                " @ " +
                fmtMoney(q.price) +
                (q.change_pct != null
                    ? " (" + (q.change_pct >= 0 ? "+" : "") + fmtNum(q.change_pct, 2) + "%)"
                    : "");
        });
    }

    if (!readOnly && searchIn) {
        searchIn.addEventListener("input", function () {
            var q = searchIn.value.trim().toUpperCase();
            clearTimeout(searchTimer);
            if (q.length < 1) {
                closeDd();
                return;
            }
            searchTimer = setTimeout(function () {
                getJSON("/api/search?q=" + encodeURIComponent(q)).then(function (res) {
                    if (!res.ok || !searchDd) return;
                    var results = res.d.results || [];
                    searchDd.innerHTML = "";
                    if (!results.length) {
                        closeDd();
                        return;
                    }
                    results.forEach(function (row) {
                        var b = document.createElement("button");
                        b.type = "button";
                        b.innerHTML =
                            "<strong>" +
                            row.symbol +
                            "</strong> — " +
                            (row.name || "");
                        b.addEventListener("click", function () {
                            searchIn.value = row.symbol;
                            closeDd();
                            showQuote(row.symbol);
                        });
                        searchDd.appendChild(b);
                    });
                    searchDd.classList.add("open");
                });
            }, 250);
        });
        document.addEventListener("click", function (e) {
            if (!searchDd || !searchIn) return;
            if (e.target !== searchIn && !searchDd.contains(e.target)) closeDd();
        });
    }

    function doTrade(side) {
        if (readOnly) return;
        var sym = selectedSymbol || (searchIn && searchIn.value.trim().toUpperCase());
        var sh = sharesIn ? parseFloat(sharesIn.value) : NaN;
        if (!sym) {
            alert("Enter a symbol.");
            return;
        }
        if (!sh || sh <= 0 || isNaN(sh)) {
            alert("Enter a valid share amount.");
            return;
        }
        var url = side === "buy" ? "/api/paper/buy" : "/api/paper/sell";
        fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ symbol: sym, shares: sh }),
        })
            .then(function (r) {
                return r.json().then(function (d) {
                    return { ok: r.ok, d: d };
                });
            })
            .then(function (res) {
                if (!res.ok) {
                    alert(res.d.error || "Order failed");
                    return;
                }
                loadAll();
                if (sharesIn) sharesIn.value = "";
            })
            .catch(function () {
                alert("Network error.");
            });
    }

    var btnBuy = document.getElementById("paper-btn-buy");
    var btnSell = document.getElementById("paper-btn-sell");
    if (btnBuy) btnBuy.addEventListener("click", function () { doTrade("buy"); });
    if (btnSell) btnSell.addEventListener("click", function () { doTrade("sell"); });

    bindEquityTabs();
    loadAll();
})();

