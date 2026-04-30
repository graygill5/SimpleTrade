(function () {
    var roomListEl = document.getElementById("social-room-list");
    var titleEl = document.getElementById("social-room-title");
    var descEl = document.getElementById("social-room-desc");
    var kindEl = document.getElementById("social-room-kind");
    var messagesEl = document.getElementById("social-messages");
    var composer = document.getElementById("social-composer");
    var inputEl = document.getElementById("social-input");
    var fileEl = document.getElementById("social-file");
    var fileNoticeEl = document.getElementById("social-file-notice");
    var fileNoticeMsgEl = document.getElementById("social-file-notice-msg");
    var pollTimer = null;
    var rooms = [];
    var friendsCache = [];
    var dmPickSelected = null;
    var activeRoomId = null;
    var activeRoomKind = "global";
    var lastMsgId = 0;
    var bootstrapDone = false;

    function updateAttachmentNotice() {
        if (!fileNoticeEl || !fileNoticeMsgEl || !fileEl) return;
        var f = fileEl.files && fileEl.files[0];
        if (!f) {
            fileNoticeEl.hidden = true;
            fileNoticeMsgEl.textContent = "";
            return;
        }
        fileNoticeEl.hidden = false;
        var name = f.name || "attachment";
        var mime = (f.type || "").toLowerCase();
        var isPdf =
            mime.indexOf("pdf") !== -1 || /\.pdf$/i.test(name);
        var isImage =
            mime.indexOf("image/") === 0 ||
            /\.(png|jpe?g|gif|webp)$/i.test(name);
        if (isPdf) {
            fileNoticeMsgEl.textContent =
                "PDF attached (" +
                name +
                "). It will be sent when you click Send.";
        } else if (isImage) {
            fileNoticeMsgEl.textContent =
                "Image attached (" +
                name +
                "). It will be sent when you click Send.";
        } else {
            fileNoticeMsgEl.textContent =
                "File attached (" +
                name +
                "). It will be sent when you click Send.";
        }
    }

    function api(url, opts) {
        return fetch(url, opts || {}).then(function (r) {
            if (r.status === 401) {
                window.location.href = "/";
                return Promise.reject(new Error("auth"));
            }
            var ct = r.headers.get("content-type") || "";
            if (ct.indexOf("application/json") === -1) {
                return { ok: r.ok, status: r.status, d: {} };
            }
            return r.json().then(function (d) {
                return { ok: r.ok, status: r.status, d: d };
            });
        });
    }

    function escapeHtml(s) {
        var d = document.createElement("div");
        d.textContent = s == null ? "" : String(s);
        return d.innerHTML;
    }

    function clearGroupInviteFeedback() {
        var el = document.getElementById("social-invite-feedback");
        if (!el) return;
        el.hidden = true;
        el.textContent = "";
        el.className = "social-invite-feedback";
    }

    function setGroupInviteFeedback(text, kind) {
        var el = document.getElementById("social-invite-feedback");
        if (!el) return;
        if (!text) {
            clearGroupInviteFeedback();
            return;
        }
        el.hidden = false;
        el.textContent = text;
        el.className =
            "social-invite-feedback" +
            (kind === "success" ? " is-success" : kind === "error" ? " is-error" : "");
    }

    function renderRooms() {
        if (!roomListEl) return;
        roomListEl.innerHTML = "";
        rooms.forEach(function (r) {
            var li = document.createElement("li");
            li.className =
                "social-room-item" + (r.id === activeRoomId ? " active" : "");
            li.setAttribute("data-id", String(r.id));
            li.setAttribute("data-kind", r.kind);
            if (r.kind === "global") {
                li.innerHTML =
                    '<span class="social-live-dot" aria-hidden="true"></span>' +
                    '<span class="social-live-label">' +
                    escapeHtml(r.label || r.name || "Live chat") +
                    "</span>";
            } else {
                li.textContent = r.label || r.name || "Room";
            }
            li.addEventListener("click", function () {
                selectRoom(r);
            });
            roomListEl.appendChild(li);
        });
    }

    function selectRoom(room) {
        if (!room) return;
        activeRoomId = room.id;
        activeRoomKind = room.kind || "global";
        lastMsgId = 0;
        if (titleEl) {
            titleEl.textContent = room.label || room.name || "Chat";
        }
        if (descEl) {
            descEl.textContent = room.subtitle || "";
        }
        if (kindEl) {
            kindEl.textContent =
                room.kind === "global"
                    ? "Everyone"
                    : room.kind === "dm"
                      ? "Direct message"
                      : room.kind === "group"
                        ? "Trading group"
                        : "";
        }
        var invite = document.getElementById("social-group-invite");
        var inviteFormWrap = document.getElementById("social-invite-form-wrap");
        var inviteMemberNotice = document.getElementById(
            "social-invite-member-notice"
        );
        if (invite) {
            if (room.kind !== "group") {
                invite.hidden = true;
            } else {
                invite.hidden = false;
                var canInviteToGroup =
                    room.my_role == null || room.my_role === "owner";
                if (inviteFormWrap) {
                    inviteFormWrap.hidden = !canInviteToGroup;
                }
                if (inviteMemberNotice) {
                    inviteMemberNotice.hidden = canInviteToGroup;
                }
            }
        }
        clearGroupInviteFeedback();
        renderRooms();
        stopPoll();
        loadMessages(true);
        startPoll();
    }

    function attachmentHtml(m) {
        if (!m.attachment || !m.attachment.url) return "";
        var mime = (m.attachment.mime || "").toLowerCase();
        var url = m.attachment.url;
        var fn = m.attachment.filename || "file";
        if (mime.indexOf("image/") === 0) {
            return (
                '<div class="social-msg-attach"><img src="' +
                escapeHtml(url) +
                '" alt="" loading="lazy" /></div>'
            );
        }
        return (
            '<div class="social-msg-attach"><a class="social-attach-link" href="' +
            escapeHtml(url) +
            '" target="_blank" rel="noopener noreferrer">' +
            escapeHtml(fn) +
            "</a></div>"
        );
    }

    function appendMessages(msgs, replace) {
        if (!messagesEl) return;
        if (replace) messagesEl.innerHTML = "";
        if (!msgs || !msgs.length) {
            if (replace) {
                messagesEl.innerHTML =
                    '<p class="empty social-empty">No messages yet. Say hello!</p>';
            }
            return;
        }
        msgs.forEach(function (m) {
            if (
                messagesEl.querySelector(
                    '.social-msg[data-id="' + String(m.id) + '"]'
                )
            ) {
                return;
            }
            if (m.id > lastMsgId) lastMsgId = m.id;
            var div = document.createElement("div");
            div.className = "social-msg";
            div.setAttribute("data-id", String(m.id));
            var when = escapeHtml(m.created_at || "");
            var who = escapeHtml(m.username || "");
            var body = (m.body || "").trim();
            var bodyHtml = body
                ? '<div class="social-msg-body">' + escapeHtml(body) + "</div>"
                : "";
            var att = attachmentHtml(m);
            if (!bodyHtml && !att) {
                bodyHtml = '<div class="social-msg-body">(attachment)</div>';
            }
            div.innerHTML =
                '<div class="social-msg-meta"><span class="social-msg-user">' +
                who +
                '</span> <span class="social-msg-time">' +
                when +
                "</span></div>" +
                att +
                bodyHtml;
            var empty = messagesEl.querySelector(".social-empty");
            if (empty) empty.remove();
            messagesEl.appendChild(div);
        });
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function loadMessages(replace) {
        if (activeRoomId == null) return;
        var url = "/api/social/room/" + activeRoomId + "/messages";
        if (!replace && lastMsgId > 0) {
            url += "?after_id=" + lastMsgId;
        }
        api(url).then(function (res) {
            if (!res.ok) return;
            var msgs = res.d.messages || [];
            if (replace) {
                lastMsgId = 0;
                msgs.forEach(function (m) {
                    if (m.id > lastMsgId) lastMsgId = m.id;
                });
                appendMessages(msgs, true);
            } else if (msgs.length) {
                appendMessages(msgs, false);
            }
        });
    }

    function startPoll() {
        stopPoll();
        pollTimer = setInterval(function () {
            if (activeRoomId != null && !document.hidden) {
                loadMessages(false);
            }
        }, 2800);
    }

    function stopPoll() {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    }

    function refreshBootstrap() {
        var prevId = activeRoomId;
        return api("/api/social/bootstrap").then(function (res) {
            if (!res.ok) return;
            rooms = res.d.rooms || [];
            friendsCache = res.d.friends || [];
            renderRooms();
            renderFriends(res.d);
            if (prevId) {
                var r = rooms.find(function (x) {
                    return x.id === prevId;
                });
                if (r) {
                    selectRoom(r);
                    return res.d;
                }
            }
            if (!bootstrapDone) {
                bootstrapDone = true;
                var g = rooms.find(function (x) {
                    return x.kind === "global";
                });
                if (g) selectRoom(g);
            }
            return res.d;
        });
    }

    function renderFriends(data) {
        friendsCache = data.friends || [];
        var inc = document.getElementById("social-incoming");
        var fr = document.getElementById("social-friends");
        if (data.profile) {
            var dn = document.getElementById("social-display-name");
            var bio = document.getElementById("social-bio");
            if (dn) dn.value = data.profile.display_name || "";
            if (bio) bio.value = data.profile.bio || "";
        }
        var outg = document.getElementById("social-outgoing");
        if (outg) {
            outg.innerHTML = "";
            var outgoing = data.outgoing_requests || [];
            if (!outgoing.length) {
                outg.innerHTML = '<li class="empty">None</li>';
            } else {
                outgoing.forEach(function (req) {
                    var li = document.createElement("li");
                    li.className = "social-out-item";
                    li.textContent = "→ " + req.to_user;
                    outg.appendChild(li);
                });
            }
        }
        if (inc) {
            inc.innerHTML = "";
            var incoming = data.incoming_requests || [];
            if (!incoming.length) {
                inc.innerHTML = '<li class="empty">None</li>';
            } else {
                incoming.forEach(function (req) {
                    var li = document.createElement("li");
                    li.className = "social-request-item";
                    li.innerHTML =
                        '<div class="social-req-main">' +
                        '<span class="social-req-label">Friend request</span>' +
                        '<span class="social-req-user">' +
                        escapeHtml(req.from_user) +
                        "</span></div>" +
                        '<div class="social-req-actions">' +
                        '<button type="button" class="btn btn-primary social-req-accept" data-accept="' +
                        escapeHtml(req.from_user) +
                        '">Accept</button>' +
                        '<button type="button" class="btn social-req-decline" data-decline="' +
                        escapeHtml(req.from_user) +
                        '">Decline</button></div>';
                    inc.appendChild(li);
                });
                inc.querySelectorAll("[data-accept]").forEach(function (btn) {
                    btn.addEventListener("click", function () {
                        respondFriend(btn.getAttribute("data-accept"), true);
                    });
                });
                inc.querySelectorAll("[data-decline]").forEach(function (btn) {
                    btn.addEventListener("click", function () {
                        respondFriend(btn.getAttribute("data-decline"), false);
                    });
                });
            }
        }
        if (fr) {
            fr.innerHTML = "";
            var friends = data.friends || [];
            if (!friends.length) {
                fr.innerHTML = '<li class="empty">No friends yet</li>';
            } else {
                friends.forEach(function (name) {
                    var li = document.createElement("li");
                    li.className = "social-friend-item";
                    li.innerHTML =
                        '<div class="social-friend-main">' +
                        '<span class="social-friend-label">Friend</span>' +
                        '<span class="social-friend-name">' +
                        escapeHtml(name) +
                        "</span></div>" +
                        '<div class="social-req-actions">' +
                        '<button type="button" class="btn social-friend-msg" data-user="' +
                        escapeHtml(name) +
                        '">Message</button>' +
                        '<button type="button" class="btn social-friend-profile" data-profile-user="' +
                        escapeHtml(name) +
                        '">Profile</button></div>';
                    fr.appendChild(li);
                });
                fr.querySelectorAll(".social-friend-msg").forEach(function (btn) {
                    btn.addEventListener("click", function () {
                        openDm(btn.getAttribute("data-user"));
                    });
                });
                fr.querySelectorAll(".social-friend-profile").forEach(function (btn) {
                    btn.addEventListener("click", function () {
                        openFriendProfile(btn.getAttribute("data-profile-user"));
                    });
                });
            }
        }
    }

    function hideFriendProfileModal() {
        var m = document.getElementById("social-modal-friend-profile");
        if (m) m.hidden = true;
    }

    function openFriendProfile(username) {
        if (!username) return;
        var m = document.getElementById("social-modal-friend-profile");
        var sub = document.getElementById("social-friend-profile-sub");
        var stats = document.getElementById("social-friend-learning-stats");
        var link = document.getElementById("social-friend-portfolio-link");
        if (!m || !sub || !stats || !link) return;
        sub.textContent = "Loading profile...";
        stats.textContent = "Loading learning stats...";
        link.href = "/portfolio";
        link.setAttribute("aria-disabled", "true");
        api("/api/social/profile/" + encodeURIComponent(username)).then(function (res) {
            if (!res.ok) {
                sub.textContent = res.d.error || "Could not load profile.";
                stats.textContent = "";
                link.href = "/portfolio";
                link.setAttribute("aria-disabled", "true");
                m.hidden = false;
                return;
            }
            var p = res.d.profile || {};
            var l = res.d.learning || {};
            sub.textContent =
                (p.display_name || username) +
                (p.bio ? " — " + p.bio : "");
            stats.innerHTML =
                '<div class="social-learning-grid">' +
                '<div class="social-learning-card">' +
                '<div class="social-learning-label">This week</div>' +
                '<div class="social-learning-value">' +
                String(l.completed_this_week || 0) +
                "</div>" +
                "</div>" +
                '<div class="social-learning-card">' +
                '<div class="social-learning-label">Total completed</div>' +
                '<div class="social-learning-value">' +
                String(l.total_completed || 0) +
                "</div>" +
                "</div>" +
                "</div>";
            if (res.d.can_view_portfolio) {
                link.href = "/portfolio/view/" + encodeURIComponent(username);
                link.removeAttribute("aria-disabled");
            } else {
                link.href = "#";
                link.setAttribute("aria-disabled", "true");
            }
            m.hidden = false;
        });
    }

    function respondFriend(fromUser, accept) {
        api("/api/social/friends/respond", {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ from_username: fromUser, accept: accept }),
        }).then(function (res) {
            if (!res.ok) {
                alert(res.d.error || "Failed");
                return;
            }
            refreshBootstrap();
        });
    }

    function renderDmPickList() {
        var listEl = document.getElementById("social-dm-list");
        var searchInp = document.getElementById("social-dm-search");
        if (!listEl) return;
        var q = (searchInp && searchInp.value) || "";
        q = q.trim().toLowerCase();
        listEl.innerHTML = "";
        if (!friendsCache.length) {
            listEl.innerHTML =
                '<p class="empty social-dm-list-empty">No friends yet — add someone first</p>';
            dmPickSelected = null;
            return;
        }
        var names = friendsCache.slice().sort(function (a, b) {
            return a.localeCompare(b, undefined, { sensitivity: "base" });
        });
        if (q) {
            names = names.filter(function (n) {
                return n.toLowerCase().indexOf(q) !== -1;
            });
        }
        if (dmPickSelected && names.indexOf(dmPickSelected) === -1) {
            dmPickSelected = null;
        }
        if (!names.length) {
            listEl.innerHTML =
                '<p class="empty social-dm-list-empty">No friends match that search</p>';
            return;
        }
        names.forEach(function (name) {
            var btn = document.createElement("button");
            btn.type = "button";
            btn.className =
                "social-dm-pick-row" +
                (dmPickSelected === name ? " is-selected" : "");
            btn.setAttribute("data-user", name);
            btn.setAttribute("role", "option");
            btn.setAttribute(
                "aria-selected",
                dmPickSelected === name ? "true" : "false"
            );
            btn.textContent = name;
            listEl.appendChild(btn);
        });
    }

    function openDm(username) {
        api("/api/social/dm", {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ with_username: username }),
        }).then(function (res) {
            if (!res.ok) {
                alert(res.d.error || "Could not open DM");
                return;
            }
            var rid = res.d.room_id;
            hideDmModal();
            refreshBootstrap().then(function () {
                var r = rooms.find(function (x) {
                    return x.id === rid;
                });
                if (r) selectRoom(r);
            });
        });
    }

    function buildGroupFriendCheckboxes() {
        var box = document.getElementById("social-group-friends-picks");
        if (!box) return;
        box.innerHTML = "";
        if (!friendsCache.length) {
            box.innerHTML =
                '<p class="empty" style="margin:0;">Add friends first, then you can include them in a new group.</p>';
            return;
        }
        friendsCache.forEach(function (name) {
            var id = "gc-f-" + name.replace(/[^a-zA-Z0-9_-]/g, "_");
            var row = document.createElement("label");
            row.className = "social-check-row";
            row.innerHTML =
                '<input type="checkbox" id="' +
                id +
                '" value="' +
                escapeHtml(name) +
                '" /> <span>' +
                escapeHtml(name) +
                "</span>";
            box.appendChild(row);
        });
    }

    function showGroupModal() {
        var m = document.getElementById("social-modal-group");
        var nm = document.getElementById("social-group-name");
        if (nm) nm.value = "";
        buildGroupFriendCheckboxes();
        if (m) m.hidden = false;
    }

    function hideGroupModal() {
        var m = document.getElementById("social-modal-group");
        if (m) m.hidden = true;
    }

    function showDmModal() {
        var m = document.getElementById("social-modal-dm");
        var searchInp = document.getElementById("social-dm-search");
        if (!m) return;
        dmPickSelected = null;
        if (searchInp) searchInp.value = "";
        renderDmPickList();
        m.hidden = false;
        if (searchInp) {
            setTimeout(function () {
                searchInp.focus();
            }, 0);
        }
    }

    function hideDmModal() {
        var m = document.getElementById("social-modal-dm");
        if (m) m.hidden = true;
    }

    document.getElementById("social-btn-new-group") &&
        document
            .getElementById("social-btn-new-group")
            .addEventListener("click", showGroupModal);
    document.getElementById("social-group-cancel") &&
        document
            .getElementById("social-group-cancel")
            .addEventListener("click", hideGroupModal);
    document.getElementById("social-modal-group") &&
        document.getElementById("social-modal-group").addEventListener("click", function (e) {
            if (e.target.id === "social-modal-group") hideGroupModal();
        });

    document.getElementById("social-group-create") &&
        document
            .getElementById("social-group-create")
            .addEventListener("click", function () {
                var nmIn = document.getElementById("social-group-name");
                var name = nmIn ? nmIn.value.trim() : "";
                if (name.length < 2) {
                    alert("Enter a group name (at least 2 characters).");
                    return;
                }
                var picks = [];
                document
                    .querySelectorAll(
                        "#social-group-friends-picks input[type=checkbox]:checked"
                    )
                    .forEach(function (cb) {
                        picks.push(cb.value);
                    });
                api("/api/social/groups", {
                    method: "POST",
                    credentials: "same-origin",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        name: name,
                        member_usernames: picks,
                    }),
                }).then(function (res) {
                    if (!res.ok) {
                        alert(res.d.error || "Could not create group");
                        return;
                    }
                    var rid = res.d.room_id;
                    hideGroupModal();
                    refreshBootstrap().then(function () {
                        var r = rooms.find(function (x) {
                            return x.id === rid;
                        });
                        if (r) selectRoom(r);
                    });
                });
            });

    document.getElementById("social-btn-new-dm") &&
        document
            .getElementById("social-btn-new-dm")
            .addEventListener("click", showDmModal);
    document.getElementById("social-dm-cancel") &&
        document
            .getElementById("social-dm-cancel")
            .addEventListener("click", hideDmModal);
    document.getElementById("social-modal-dm") &&
        document.getElementById("social-modal-dm").addEventListener("click", function (e) {
            if (e.target.id === "social-modal-dm") hideDmModal();
        });
    document.getElementById("social-dm-list") &&
        document.getElementById("social-dm-list").addEventListener("click", function (e) {
            var row = e.target.closest(".social-dm-pick-row");
            if (!row) return;
            dmPickSelected = row.getAttribute("data-user") || null;
            this.querySelectorAll(".social-dm-pick-row").forEach(function (r) {
                var on = r === row;
                r.classList.toggle("is-selected", on);
                r.setAttribute("aria-selected", on ? "true" : "false");
            });
        });
    document.getElementById("social-dm-search") &&
        document
            .getElementById("social-dm-search")
            .addEventListener("input", function () {
                renderDmPickList();
            });
    document.getElementById("social-dm-open") &&
        document
            .getElementById("social-dm-open")
            .addEventListener("click", function () {
                if (!dmPickSelected) {
                    alert("Pick a friend from the list.");
                    return;
                }
                openDm(dmPickSelected);
            });
    document.getElementById("social-friend-profile-close") &&
        document
            .getElementById("social-friend-profile-close")
            .addEventListener("click", hideFriendProfileModal);
    document.getElementById("social-modal-friend-profile") &&
        document
            .getElementById("social-modal-friend-profile")
            .addEventListener("click", function (e) {
                if (e.target.id === "social-modal-friend-profile") {
                    hideFriendProfileModal();
                }
            });

    document.getElementById("social-friend-btn") &&
        document
            .getElementById("social-friend-btn")
            .addEventListener("click", function () {
                var inp = document.getElementById("social-friend-add");
                var u = inp && inp.value.trim();
                if (!u) return;
                api("/api/social/friends/request", {
                    method: "POST",
                    credentials: "same-origin",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ to_username: u }),
                }).then(function (res) {
                    if (!res.ok) {
                        alert(res.d.error || "Request failed");
                        return;
                    }
                    inp.value = "";
                    refreshBootstrap();
                });
            });

    document.getElementById("social-save-profile") &&
        document
            .getElementById("social-save-profile")
            .addEventListener("click", function () {
                var dn = document.getElementById("social-display-name");
                var bio = document.getElementById("social-bio");
                api("/api/social/profile", {
                    method: "PUT",
                    credentials: "same-origin",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        display_name: dn ? dn.value : "",
                        bio: bio ? bio.value : "",
                    }),
                }).then(function (res) {
                    if (!res.ok) {
                        alert(res.d.error || "Save failed");
                        return;
                    }
                    alert("Profile saved.");
                });
            });

    document.getElementById("social-invite-input") &&
        document
            .getElementById("social-invite-input")
            .addEventListener("input", function () {
                clearGroupInviteFeedback();
            });
    document.getElementById("social-invite-btn") &&
        document
            .getElementById("social-invite-btn")
            .addEventListener("click", function () {
                if (activeRoomKind !== "group" || !activeRoomId) return;
                var wrap = document.getElementById("social-invite-form-wrap");
                if (wrap && wrap.hidden) return;
                var inp = document.getElementById("social-invite-input");
                var u = inp && inp.value.trim();
                if (!u) {
                    setGroupInviteFeedback("Enter a username to invite.", "error");
                    return;
                }
                clearGroupInviteFeedback();
                api("/api/social/groups/" + activeRoomId + "/invite", {
                    method: "POST",
                    credentials: "same-origin",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ username: u }),
                }).then(function (res) {
                    if (!res.ok) {
                        setGroupInviteFeedback(
                            res.d.error || "Invite failed.",
                            "error"
                        );
                        return;
                    }
                    if (inp) inp.value = "";
                    setGroupInviteFeedback(
                        "Invited — they are in the group now.",
                        "success"
                    );
                    refreshBootstrap();
                });
            });

    fileEl &&
        fileEl.addEventListener("change", function () {
            updateAttachmentNotice();
        });
    document.getElementById("social-file-clear") &&
        document
            .getElementById("social-file-clear")
            .addEventListener("click", function () {
                if (fileEl) fileEl.value = "";
                updateAttachmentNotice();
            });

    if (composer) {
        composer.addEventListener("submit", function (e) {
            e.preventDefault();
            if (activeRoomId == null) return;
            var t = inputEl ? inputEl.value.trim() : "";
            var hasFile =
                fileEl && fileEl.files && fileEl.files.length > 0;
            if (!t && !hasFile) {
                alert("Type a message or attach a file.");
                return;
            }
            var url = "/api/social/room/" + activeRoomId + "/messages";
            var p;
            if (hasFile) {
                var fd = new FormData();
                fd.append("body", t);
                fd.append("file", fileEl.files[0]);
                p = fetch(url, {
                    method: "POST",
                    credentials: "same-origin",
                    body: fd,
                }).then(function (r) {
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
            } else {
                p = api(url, {
                    method: "POST",
                    credentials: "same-origin",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ body: t }),
                });
            }
            p.then(function (res) {
                if (!res.ok) {
                    alert(res.d.error || "Send failed");
                    return;
                }
                if (inputEl) inputEl.value = "";
                if (fileEl) fileEl.value = "";
                updateAttachmentNotice();
                loadMessages(true);
            }).catch(function (err) {
                if (err && err.message === "auth") return;
                alert("Network error — try again or use a JPEG/PNG/PDF under 8 MB.");
            });
        });
    }

    document.querySelectorAll(".social-tab").forEach(function (tab) {
        tab.addEventListener("click", function () {
            var name = tab.getAttribute("data-tab");
            document.querySelectorAll(".social-tab").forEach(function (t) {
                t.classList.toggle("active", t === tab);
            });
            var pf = document.getElementById("social-panel-friends");
            var pp = document.getElementById("social-panel-profile");
            if (name === "friends") {
                if (pf) pf.hidden = false;
                if (pp) pp.hidden = true;
            } else {
                if (pf) pf.hidden = true;
                if (pp) pp.hidden = false;
            }
        });
    });

    refreshBootstrap();

    document.addEventListener("visibilitychange", function () {
        if (!document.hidden && activeRoomId != null) {
            loadMessages(false);
        }
    });
})();
