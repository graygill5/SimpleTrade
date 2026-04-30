(function () {
    var root = document.getElementById("learn-app");
    var grid = document.getElementById("learn-module-grid");
    var modal = document.getElementById("learn-modal");
    var modalTitle = document.getElementById("learn-modal-title");
    var modalTag = document.getElementById("learn-modal-tagline");
    var lessonBody = document.getElementById("learn-lesson-body");
    var lessonGraphic = document.getElementById("learn-module-graphic");
    var quizForm = document.getElementById("learn-quiz-form");
    var quizFields = document.getElementById("learn-quiz-fields");
    var quizFeedback = document.getElementById("learn-quiz-feedback");
    var genQuizBtn = document.getElementById("learn-gen-quiz-btn");
    var aiPanel = document.getElementById("learn-ai-panel");
    var aiBtn = document.getElementById("learn-ai-btn");
    var aiOut = document.getElementById("learn-ai-output");
    var progressFill = document.getElementById("learn-progress-fill");
    var progressText = document.getElementById("learn-progress-text");
    var calDateEl = document.getElementById("learn-calendar-date");
    var bonusStatusEl = document.getElementById("learn-bonus-status");

    var aiReady = root && root.getAttribute("data-ai-ready") === "1";
    var state = null;
    var activeModuleId = null;
    var moduleDetailCache = {};
    var generatedQuizCache = {};

    function escapeHtml(s) {
        var d = document.createElement("div");
        d.textContent = s == null ? "" : String(s);
        return d.innerHTML;
    }

    function lessonToHtml(raw) {
        var parts = String(raw).split(/\*\*/);
        var html = "";
        for (var i = 0; i < parts.length; i++) {
            if (i % 2 === 1) {
                html += "<strong>" + escapeHtml(parts[i]) + "</strong>";
            } else {
                html += escapeHtml(parts[i]);
            }
        }
        return html;
    }

    function api(url, opts) {
        return fetch(url, opts || {}).then(function (r) {
            if (r.status === 401) {
                window.location.href = "/";
                return Promise.reject(new Error("auth"));
            }
            var ct = r.headers.get("content-type") || "";
            if (ct.indexOf("application/json") === -1) {
                return { ok: r.ok, d: {} };
            }
            return r.json().then(function (d) {
                return { ok: r.ok, d: d };
            });
        });
    }

    function renderProgress() {
        if (!state || !progressFill || !progressText || !calDateEl || !bonusStatusEl) return;
        calDateEl.textContent = state.calendar_date || "—";
        var n = state.module_count || 10;
        var c = state.completed_today_count || 0;
        var pct = n ? Math.round((c / n) * 100) : 0;
        progressFill.style.width = pct + "%";
        progressText.textContent = c + " / " + n + " modules today";
        if (state.bonus_claimed_today) {
            bonusStatusEl.textContent = "Claimed ✓";
        } else if (state.all_modules_completed_today) {
            bonusStatusEl.textContent = "Unlocked ✓";
        } else {
            bonusStatusEl.textContent = "Locked";
        }
    }

    function renderGrid() {
        if (!grid || !state || !state.modules) return;
        grid.innerHTML = "";
        state.modules.forEach(function (m) {
            var card = document.createElement("button");
            card.type = "button";
            card.className =
                "learn-card" + (m.completed_today ? " is-done" : "");
            card.innerHTML =
                '<span class="learn-card-icon">' +
                escapeHtml(m.icon || "MOD") +
                '</span><div class="learn-card-main"><div class="learn-card-title">' +
                escapeHtml(m.title) +
                '</div><div class="learn-card-tag">' +
                escapeHtml(m.tagline || "") +
                '</div></div><div class="learn-card-meta">' +
                (m.completed_today
                    ? '<span class="learn-done-pill">Done today</span>'
                    : '<span class="learn-reward-pill">$' +
                      (m.reward_usd != null ? m.reward_usd.toLocaleString() : "10,000") +
                      "</span>") +
                "</div>";
            card.addEventListener("click", function () {
                openModule(m.id);
            });
            grid.appendChild(card);
        });
    }

    function openModule(mid) {
        activeModuleId = mid;
        if (quizFeedback) {
            quizFeedback.hidden = true;
            quizFeedback.textContent = "";
        }
        if (aiOut) {
            aiOut.hidden = true;
            aiOut.innerHTML = "";
        }
        if (moduleDetailCache[mid]) {
            fillModal(moduleDetailCache[mid]);
            if (modal) modal.hidden = false;
            return;
        }
        api("/api/learning/module/" + encodeURIComponent(mid)).then(function (res) {
            if (!res.ok || !res.d.module) return;
            moduleDetailCache[mid] = res.d.module;
            fillModal(res.d.module);
            if (modal) modal.hidden = false;
        });
    }

    function fillModal(mod) {
        var mid = mod.id || "";
        var doneToday = false;
        if (state && state.modules) {
            state.modules.forEach(function (x) {
                if (x.id === mid && x.completed_today) doneToday = true;
            });
        }
        if (modalTitle) modalTitle.textContent = mod.title || "";
        if (modalTag) modalTag.textContent = mod.tagline || "";
        if (lessonGraphic) {
            lessonGraphic.innerHTML =
                '<div class="learn-module-graphic-chip">' +
                escapeHtml(mod.icon || "MODULE") +
                "</div>" +
                '<div class="learn-module-graphic-title">' +
                escapeHtml(mod.title || "Learning module") +
                "</div>";
        }
        if (lessonBody) {
            lessonBody.innerHTML = "";
            (mod.lessons || []).forEach(function (para) {
                var p = document.createElement("p");
                p.className = "learn-lesson-p";
                p.innerHTML = lessonToHtml(para);
                lessonBody.appendChild(p);
            });
        }
        renderQuizForModule(mid);
        var submitBtn = document.getElementById("learn-submit-quiz");
        if (submitBtn) {
            var hasQuiz =
                generatedQuizCache[mid] &&
                generatedQuizCache[mid].questions &&
                generatedQuizCache[mid].questions.length > 0;
            submitBtn.disabled = doneToday || !hasQuiz;
            submitBtn.textContent = doneToday
                ? "Completed today — come back tomorrow"
                : hasQuiz
                  ? "Submit answers"
                  : "Generate quiz first";
        }
        if (genQuizBtn) genQuizBtn.disabled = doneToday || !aiReady;
        if (quizFeedback) {
            quizFeedback.hidden = true;
            if (doneToday) {
                quizFeedback.hidden = false;
                quizFeedback.className = "learn-quiz-feedback is-muted";
                quizFeedback.textContent =
                    "You already earned today's reward for this module.";
            }
        }
        if (aiPanel) {
            aiPanel.hidden = !aiReady;
        }
    }

    function renderQuizForModule(mid) {
        if (!quizFields) return;
        quizFields.innerHTML = "";
        var qz = generatedQuizCache[mid];
        if (!qz || !qz.questions || !qz.questions.length) {
            var empty = document.createElement("p");
            empty.className = "learn-quiz-empty";
            empty.textContent = aiReady
                ? "Generate a 10-question AI quiz to attempt this module reward."
                : "AI quiz generation is unavailable until OpenAI is configured.";
            quizFields.appendChild(empty);
            return;
        }
        qz.questions.forEach(function (q, qi) {
            var wrap = document.createElement("fieldset");
            wrap.className = "learn-q-fieldset";
            wrap.setAttribute("data-qi", String(qi));
            var leg = document.createElement("legend");
            leg.className = "learn-q-legend";
            leg.textContent = "Q" + (qi + 1) + ". " + (q.question || "");
            wrap.appendChild(leg);
            (q.choices || []).forEach(function (ch, ci) {
                var lab = document.createElement("label");
                lab.className = "learn-choice";
                lab.setAttribute("data-choice-index", String(ci));
                lab.innerHTML =
                    '<input type="radio" name="q' +
                    qi +
                    '" value="' +
                    ci +
                    '" required /> <span>' +
                    escapeHtml(ch) +
                    "</span>";
                wrap.appendChild(lab);
            });
            quizFields.appendChild(wrap);
        });
    }

    function applyGradeHighlight(grade) {
        if (!quizFields || !grade) return;
        var incorrect = grade.incorrect_indexes || [];
        var correct = grade.correct_indexes || [];
        var fields = quizFields.querySelectorAll(".learn-q-fieldset");
        for (var i = 0; i < fields.length; i++) {
            fields[i].classList.remove("is-correct", "is-incorrect");
            var labels = fields[i].querySelectorAll(".learn-choice");
            for (var j = 0; j < labels.length; j++) {
                labels[j].classList.remove("is-correct", "is-incorrect");
            }
            var ci = correct[i];
            if (typeof ci === "number" && ci >= 0) {
                var good = fields[i].querySelector(
                    '.learn-choice[data-choice-index="' + ci + '"]'
                );
                if (good) good.classList.add("is-correct");
            }
            if (incorrect.indexOf(i) !== -1) {
                fields[i].classList.add("is-incorrect");
                var picked = fields[i].querySelector("input:checked");
                if (picked) {
                    var bad = picked.closest(".learn-choice");
                    if (bad && !bad.classList.contains("is-correct")) {
                        bad.classList.add("is-incorrect");
                    }
                }
            } else {
                fields[i].classList.add("is-correct");
            }
        }
    }

    function closeModal() {
        if (modal) modal.hidden = true;
        activeModuleId = null;
    }

    function loadState() {
        api("/api/learning/state").then(function (res) {
            if (!res.ok || !res.d) return;
            state = res.d;
            renderProgress();
            renderGrid();
        });
    }

    if (quizForm) {
        quizForm.addEventListener("submit", function (e) {
            e.preventDefault();
            if (!activeModuleId) return;
            var qz = generatedQuizCache[activeModuleId];
            if (!qz || !qz.questions || !qz.quiz_id) return;
            var ans = [];
            var bad = false;
            for (var i = 0; i < qz.questions.length; i++) {
                var sel = quizForm.querySelector('input[name="q' + i + '"]:checked');
                if (!sel) {
                    bad = true;
                    break;
                }
                ans.push(parseInt(sel.value, 10));
            }
            if (bad) {
                if (quizFeedback) {
                    quizFeedback.hidden = false;
                    quizFeedback.className = "learn-quiz-feedback is-error";
                    quizFeedback.textContent = "Answer every question.";
                }
                return;
            }
            if (quizFeedback) quizFeedback.hidden = true;
            api("/api/learning/quiz", {
                method: "POST",
                credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    module_id: activeModuleId,
                    quiz_id: qz.quiz_id,
                    answers: ans,
                }),
            }).then(function (res) {
                if (!res.ok) {
                    if (res.d && res.d.grade) applyGradeHighlight(res.d.grade);
                    if (quizFeedback) {
                        quizFeedback.hidden = false;
                        quizFeedback.className = "learn-quiz-feedback is-error";
                        quizFeedback.textContent = res.d.error || "Try again.";
                    }
                    return;
                }
                if (quizFeedback) {
                    quizFeedback.hidden = false;
                    quizFeedback.className = "learn-quiz-feedback is-success";
                    quizFeedback.textContent = res.d.message || "Nice work!";
                }
                if (res.d && res.d.grade) applyGradeHighlight(res.d.grade);
                state = res.d.state;
                renderProgress();
                renderGrid();
            });
        });
    }

    if (genQuizBtn) {
        genQuizBtn.addEventListener("click", function () {
            if (!activeModuleId || !aiReady) return;
            genQuizBtn.disabled = true;
            genQuizBtn.textContent = "Generating quiz...";
            if (quizFeedback) quizFeedback.hidden = true;
            api("/api/learning/generate_quiz", {
                method: "POST",
                credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ module_id: activeModuleId }),
            }).then(function (res) {
                genQuizBtn.disabled = false;
                genQuizBtn.textContent = "Generate AI quiz (10 questions)";
                if (!res.ok) {
                    if (quizFeedback) {
                        quizFeedback.hidden = false;
                        quizFeedback.className = "learn-quiz-feedback is-error";
                        quizFeedback.textContent =
                            res.d.error || "Could not generate quiz.";
                    }
                    return;
                }
                generatedQuizCache[activeModuleId] = {
                    quiz_id: res.d.quiz_id,
                    questions: res.d.questions || [],
                };
                renderQuizForModule(activeModuleId);
                var submitBtn = document.getElementById("learn-submit-quiz");
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = "Submit answers";
                }
                if (quizFeedback) {
                    quizFeedback.hidden = false;
                    quizFeedback.className = "learn-quiz-feedback is-muted";
                    quizFeedback.textContent = "Quiz generated. Answer all 10 questions.";
                }
            });
        });
    }

    if (aiBtn) {
        aiBtn.addEventListener("click", function () {
            if (!activeModuleId || !aiReady) return;
            if (aiOut) {
                aiOut.hidden = false;
                aiOut.innerHTML = "<p>Generating…</p>";
            }
            api("/api/learning/ai_summary", {
                method: "POST",
                credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ module_id: activeModuleId }),
            }).then(function (res) {
                if (!aiOut) return;
                if (!res.ok) {
                    aiOut.innerHTML =
                        "<p>" + escapeHtml(res.d.error || "Could not generate.") + "</p>";
                    return;
                }
                var t = res.d.summary || "";
                aiOut.innerHTML = "<div class=\"learn-ai-prose\">" + escapeHtml(t).replace(/\n/g, "<br/>") + "</div>";
            });
        });
    }

    document.getElementById("learn-modal-close") &&
        document
            .getElementById("learn-modal-close")
            .addEventListener("click", closeModal);
    modal &&
        modal.addEventListener("click", function (e) {
            if (e.target === modal) closeModal();
        });

    loadState();
})();
