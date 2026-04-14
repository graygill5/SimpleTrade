(function () {
    var fab = document.getElementById("ai-fab");
    var panel = document.getElementById("ai-panel");
    var closeBtn = document.getElementById("ai-close");
    var msgs = document.getElementById("ai-msgs");
    var input = document.getElementById("ai-input");
    var sendBtn = document.getElementById("ai-send");

    if (!fab || !panel || !msgs) return;

    var history = [];

    function scrollBottom() {
        msgs.scrollTop = msgs.scrollHeight;
    }

    function appendBubble(role, text) {
        var div = document.createElement("div");
        div.className = "bubble " + (role === "user" ? "user" : "bot");
        div.textContent = text;
        msgs.appendChild(div);
        scrollBottom();
    }

    function openPanel() {
        panel.classList.add("open");
        if (msgs.children.length === 0) {
            appendBubble(
                "bot",
                "Hi — I can explain markets, the app, and general concepts. What would you like to explore?"
            );
        }
        setTimeout(function () {
            if (input) input.focus();
        }, 50);
    }

    function closePanel() {
        panel.classList.remove("open");
    }

    fab.addEventListener("click", function () {
        if (panel.classList.contains("open")) closePanel();
        else openPanel();
    });
    if (closeBtn) closeBtn.addEventListener("click", closePanel);

    function postChat() {
        if (!input) return;
        var t = input.value.trim();
        if (!t) return;
        input.value = "";
        appendBubble("user", t);
        history.push({ role: "user", content: t });

        var loading = document.createElement("div");
        loading.className = "bubble bot";
        loading.textContent = "…";
        msgs.appendChild(loading);
        scrollBottom();

        fetch("/api/ai/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({ messages: history }),
        })
            .then(function (r) {
                return r.json();
            })
            .then(function (data) {
                msgs.removeChild(loading);
                if (data.error) {
                    appendBubble("bot", "Sorry — " + data.error);
                    return;
                }
                var reply = data.reply || "";
                appendBubble("bot", reply);
                history.push({ role: "assistant", content: reply });
            })
            .catch(function () {
                msgs.removeChild(loading);
                appendBubble("bot", "Network error. Try again.");
            });
    }

    if (sendBtn) sendBtn.addEventListener("click", postChat);
    if (input)
        input.addEventListener("keydown", function (e) {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                postChat();
            }
        });
})();
