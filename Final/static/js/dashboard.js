(function () {
    var searchInput = document.getElementById("symbol-search");
    var searchDd = document.getElementById("search-results");
    var stockCard = document.getElementById("stock-detail");
    var stockTitle = document.getElementById("stock-title");
    var stockMeta = document.getElementById("stock-meta");
    var mPrice = document.getElementById("m-price");
    var mChg = document.getElementById("m-chg");
    var mVol = document.getElementById("m-vol");
    var mCap = document.getElementById("m-cap");
    var btnWl = document.getElementById("btn-add-wl");
    var tickerAiWrap = document.getElementById("ticker-ai-wrap");
    var tickerAiOut = document.getElementById("ticker-ai-out");
    var tickerNewsList = document.getElementById("ticker-news-list");
    var chartSection = document.getElementById("chart-section");
    var chartEmpty = document.getElementById("chart-empty");
    var chartTabs = document.getElementById("chart-tabs");
    var defaultChartRange = "1m";
    var priceChart = null;
    var selectedSymbol = null;
    var timer = null;

    function getActiveChartRange() {
        if (!chartTabs) return defaultChartRange;
        var a = chartTabs.querySelector(".chart-tab.active");
        return (a && a.getAttribute("data-range")) || defaultChartRange;
    }

    function loadChart(sym, rangeKey) {
        if (!chartSection || typeof Chart === "undefined") {
            if (chartEmpty && chartSection) {
                chartEmpty.hidden = false;
                chartEmpty.textContent =
                    typeof Chart === "undefined"
                        ? "Chart library did not load. Check your network."
                        : "";
            }
            return;
        }
        if (!sym) return;
        chartSection.hidden = false;
        if (chartEmpty) {
            chartEmpty.hidden = true;
            chartEmpty.textContent = "";
        }
        var ctx = document.getElementById("price-chart");
        if (!ctx) return;

        fetch(
            "/api/chart/" +
                encodeURIComponent(sym) +
                "?range=" +
                encodeURIComponent(rangeKey),
            { credentials: "same-origin" }
        )
            .then(function (r) {
                if (r.status === 401) {
                    window.location.href = "/";
                    return Promise.reject(new Error("auth"));
                }
                return r.json().then(function (d) {
                    return { ok: r.ok, d: d };
                });
            })
            .then(function (res) {
                if (!res) return;
                if (priceChart) {
                    priceChart.destroy();
                    priceChart = null;
                }
                if (!res.ok) {
                    if (chartEmpty) {
                        chartEmpty.hidden = false;
                        chartEmpty.textContent =
                            (res.d && res.d.error) || "Chart data unavailable.";
                    }
                    return;
                }
                var d = res.d;
                if (!d.labels || !d.labels.length) {
                    if (chartEmpty) {
                        chartEmpty.hidden = false;
                        chartEmpty.textContent = "No price points for this range.";
                    }
                    return;
                }
                if (chartEmpty) chartEmpty.hidden = true;
                priceChart = new Chart(ctx, {
                    type: "line",
                    data: {
                        labels: d.labels,
                        datasets: [
                            {
                                label: (d.symbol || sym) + " close",
                                data: d.closes,
                                borderColor: "#38bdf8",
                                backgroundColor: "rgba(56, 189, 248, 0.08)",
                                fill: true,
                                tension: 0.12,
                                pointRadius: 0,
                                borderWidth: 2,
                                spanGaps: true,
                            },
                        ],
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        interaction: { mode: "index", intersect: false },
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                callbacks: {
                                    label: function (c) {
                                        var v = c.parsed.y;
                                        return v != null && !isNaN(v)
                                            ? "Close " + Number(v).toFixed(2)
                                            : "";
                                    },
                                },
                            },
                        },
                        scales: {
                            x: {
                                grid: { color: "rgba(148,163,184,0.08)" },
                                ticks: {
                                    color: "#64748b",
                                    maxRotation: 45,
                                    maxTicksLimit: 12,
                                },
                            },
                            y: {
                                grid: { color: "rgba(148,163,184,0.08)" },
                                ticks: { color: "#64748b" },
                            },
                        },
                    },
                });
            })
            .catch(function () {
                if (chartEmpty) {
                    chartEmpty.hidden = false;
                    chartEmpty.textContent = "Could not load chart.";
                }
            });
    }

    function openSymbol(sym) {
        if (!sym) return;
        if (searchInput) searchInput.value = sym;
        var panel = document.querySelector(".search-panel");
        if (panel) {
            panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
        loadQuote(sym);
    }

    function fmtPct(x) {
        if (x == null || isNaN(x)) return "—";
        var s = (x >= 0 ? "+" : "") + x.toFixed(2) + "%";
        return s;
    }

    function fmtCap(n) {
        if (n == null || isNaN(n)) return "—";
        var x = Math.abs(n);
        if (x >= 1e12) return (n / 1e12).toFixed(2) + "T";
        if (x >= 1e9) return (n / 1e9).toFixed(2) + "B";
        if (x >= 1e6) return (n / 1e6).toFixed(2) + "M";
        if (x >= 1e3) return (n / 1e3).toFixed(2) + "K";
        return n.toFixed(0);
    }

    function fmtVol(n) {
        if (n == null || isNaN(n)) return "—";
        var x = Math.abs(n);
        if (x >= 1e9) return (n / 1e9).toFixed(2) + "B";
        if (x >= 1e6) return (n / 1e6).toFixed(2) + "M";
        if (x >= 1e3) return (n / 1e3).toFixed(2) + "K";
        return n.toFixed(0);
    }

    function showQuote(q) {
        if (!q || !stockCard) return;
        selectedSymbol = q.symbol;
        if (stockTitle) stockTitle.textContent = q.name || q.symbol;
        if (stockMeta) stockMeta.textContent = q.symbol;
        if (mPrice) mPrice.textContent = q.price != null ? Number(q.price).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—";
        if (mChg) {
            mChg.textContent = fmtPct(q.change_pct);
            mChg.className = "v num " + (q.change_pct > 0 ? "up" : q.change_pct < 0 ? "down" : "");
        }
        if (mVol) mVol.textContent = fmtVol(q.volume);
        if (mCap) mCap.textContent = fmtCap(q.market_cap);
        if (btnWl) btnWl.disabled = false;
        if (chartSection) chartSection.hidden = false;
        loadChart(selectedSymbol, getActiveChartRange());
    }

    function renderTickerNews(news) {
        if (!tickerNewsList) return;
        tickerNewsList.innerHTML = "";
        if (!news || !news.length) return;
        var hd = document.createElement("div");
        hd.className = "ticker-news-hd";
        hd.textContent = "Recent headlines (Yahoo Finance)";
        tickerNewsList.appendChild(hd);
        var ul = document.createElement("ul");
        ul.className = "ticker-news-ul";
        news.forEach(function (n) {
            var li = document.createElement("li");
            if (n.link) {
                var a = document.createElement("a");
                a.href = n.link;
                a.target = "_blank";
                a.rel = "noopener noreferrer";
                a.textContent = n.title || "";
                li.appendChild(a);
                if (n.publisher) {
                    var sp = document.createElement("span");
                    sp.className = "pub";
                    sp.textContent = n.publisher;
                    li.appendChild(sp);
                }
            } else {
                li.textContent = (n.title || "") + (n.publisher ? " — " + n.publisher : "");
            }
            ul.appendChild(li);
        });
        tickerNewsList.appendChild(ul);
    }

    function loadTickerInsight(sym) {
        if (!tickerAiWrap || !tickerAiOut) return;
        tickerAiWrap.hidden = false;
        tickerAiOut.classList.add("loading");
        tickerAiOut.textContent = "Loading AI overview and headlines…";
        renderTickerNews([]);

        fetch("/api/ai/ticker-overview", {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ symbol: sym }),
        })
            .then(function (r) {
                return r.json().then(function (data) {
                    return { ok: r.ok, data: data };
                });
            })
            .then(function (res) {
                tickerAiOut.classList.remove("loading");
                var data = res.data || {};
                if (!res.ok) {
                    tickerAiOut.textContent = data.error || "Could not load ticker insight.";
                    renderTickerNews([]);
                    return;
                }
                if (data.text) {
                    tickerAiOut.textContent = data.text;
                } else if (data.ai_error) {
                    tickerAiOut.textContent =
                        "AI overview unavailable: " + data.ai_error;
                } else {
                    tickerAiOut.textContent = "";
                }
                renderTickerNews(data.news || []);
            })
            .catch(function () {
                if (tickerAiOut) {
                    tickerAiOut.classList.remove("loading");
                    tickerAiOut.textContent = "Request failed.";
                }
            });
    }

    function loadQuote(sym) {
        fetch("/api/quote/" + encodeURIComponent(sym), { credentials: "same-origin" })
            .then(function (r) {
                if (r.status === 401) {
                    window.location.href = "/";
                    return Promise.reject(new Error("auth"));
                }
                return r.json();
            })
            .then(function (data) {
                if (!data || data.error) {
                    if (chartSection) chartSection.hidden = true;
                    if (priceChart) {
                        priceChart.destroy();
                        priceChart = null;
                    }
                    return;
                }
                showQuote(data);
                loadTickerInsight(data.symbol || sym);
            })
            .catch(function () {});
    }

    function closeDd() {
        if (searchDd) {
            searchDd.classList.remove("open");
            searchDd.innerHTML = "";
        }
    }

    function runSearch(q) {
        if (!searchDd) return;
        if (q.length < 1) {
            closeDd();
            return;
        }
        fetch("/api/search?q=" + encodeURIComponent(q), { credentials: "same-origin" })
            .then(function (r) {
                if (r.status === 401) {
                    window.location.href = "/";
                    return Promise.reject(new Error("auth"));
                }
                return r.json();
            })
            .then(function (data) {
                if (!data) return;
                var res = data.results || [];
                searchDd.innerHTML = "";
                if (!res.length) {
                    closeDd();
                    return;
                }
                res.forEach(function (row) {
                    var b = document.createElement("button");
                    b.type = "button";
                    b.innerHTML =
                        "<strong>" +
                        row.symbol +
                        "</strong> — " +
                        (row.name || "") +
                        " <span class='num'>" +
                        (row.price != null && typeof row.price === "number"
                            ? row.price.toFixed(2)
                            : "") +
                        "</span>";
                    b.addEventListener("click", function () {
                        searchInput.value = row.symbol;
                        closeDd();
                        openSymbol(row.symbol);
                    });
                    searchDd.appendChild(b);
                });
                searchDd.classList.add("open");
            })
            .catch(function () {});
    }

    if (searchInput) {
        searchInput.addEventListener("input", function () {
            var q = searchInput.value.trim();
            clearTimeout(timer);
            timer = setTimeout(function () {
                runSearch(q);
            }, 280);
        });
        searchInput.addEventListener("focus", function () {
            if (searchInput.value.trim()) runSearch(searchInput.value.trim());
        });
    }

    document.addEventListener("click", function (e) {
        if (!searchDd || !searchInput) return;
        if (e.target !== searchInput && !searchDd.contains(e.target)) closeDd();
    });

    if (chartTabs) {
        chartTabs.querySelectorAll(".chart-tab").forEach(function (btn) {
            btn.addEventListener("click", function () {
                var r = btn.getAttribute("data-range");
                if (!r) return;
                chartTabs.querySelectorAll(".chart-tab").forEach(function (b) {
                    b.classList.remove("active");
                });
                btn.classList.add("active");
                if (selectedSymbol) loadChart(selectedSymbol, r);
            });
        });
    }

    document.querySelectorAll(".ticker-jump").forEach(function (el) {
        el.addEventListener("click", function () {
            var s = el.getAttribute("data-symbol");
            if (s) openSymbol(s);
        });
        el.addEventListener("keydown", function (e) {
            if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                var s = el.getAttribute("data-symbol");
                if (s) openSymbol(s);
            }
        });
    });

    document.querySelectorAll(".wl-row").forEach(function (tr) {
        tr.addEventListener("click", function (e) {
            var el = e.target;
            if (el && el.nodeType !== 1) el = el.parentElement;
            if (el && typeof el.closest === "function" && el.closest("button[data-remove-wl]"))
                return;
            var s = tr.getAttribute("data-symbol");
            if (s) openSymbol(s);
        });
    });

    if (btnWl) {
        btnWl.addEventListener("click", function () {
            if (!selectedSymbol) return;
            btnWl.disabled = true;
            fetch("/api/watchlist", {
                method: "POST",
                credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ symbol: selectedSymbol }),
            })
                .then(function (r) {
                    if (r.status === 401) {
                        window.location.href = "/";
                        return Promise.reject(new Error("auth"));
                    }
                    return r.json();
                })
                .then(function (data) {
                    if (!data) return;
                    if (data.error) {
                        alert(data.error);
                        btnWl.disabled = false;
                        return;
                    }
                    window.location.reload();
                })
                .catch(function () {
                    btnWl.disabled = false;
                });
        });
    }

    document.querySelectorAll("[data-remove-wl]").forEach(function (btn) {
        btn.addEventListener("click", function () {
            var sym = btn.getAttribute("data-remove-wl");
            fetch("/api/watchlist/" + encodeURIComponent(sym), {
                method: "DELETE",
                credentials: "same-origin",
            })
                .then(function (r) {
                    if (r.status === 401) {
                        window.location.href = "/";
                        return;
                    }
                    window.location.reload();
                })
                .catch(function () {});
        });
    });

    var aiSum = document.getElementById("ai-summary-btn");
    var aiOut = document.getElementById("ai-summary-out");
    var aiLook = document.getElementById("ai-outlook-btn");
    var aiLookOut = document.getElementById("ai-outlook-out");

    function runAi(btn, outEl, path) {
        if (!outEl) return;
        outEl.classList.add("loading");
        outEl.textContent = "Generating…";
        if (btn) btn.disabled = true;
        fetch(path, {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
        })
            .then(function (r) {
                return r.json();
            })
            .then(function (data) {
                outEl.classList.remove("loading");
                if (data.error) {
                    outEl.textContent = data.error;
                    return;
                }
                outEl.textContent = data.text || "";
                if (btn) btn.disabled = false;
            })
            .catch(function () {
                outEl.classList.remove("loading");
                outEl.textContent = "Request failed.";
                if (btn) btn.disabled = false;
            });
    }

    if (aiSum)
        aiSum.addEventListener("click", function () {
            runAi(aiSum, aiOut, "/api/ai/market-summary");
        });
    if (aiLook)
        aiLook.addEventListener("click", function () {
            runAi(aiLook, aiLookOut, "/api/ai/outlook");
        });
})();
