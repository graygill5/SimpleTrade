"""
Chat & social: friends, rooms (global, DM, group), messages, profiles.
Attachments: images + PDF stored under uploads/chat/ (see save_chat_attachment).
"""
from __future__ import annotations

import os
import sqlite3
import uuid
from typing import Any

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.db")

CHAT_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads", "chat")
GLOBAL_ROOM_NAME = "Market Chat"
GLOBAL_ROOM_SUBTITLE = "Live — everyone can join. Discuss markets & news."
MAX_MESSAGE_LEN = 4000
MAX_GROUP_MEMBERS = 50
MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024
ALLOWED_ATTACHMENT_MIME: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}


def _normalize_upload_mime(mime: str, filename: str) -> str:
    """Map common aliases and infer type from filename when browsers send octet-stream."""
    mime = (mime or "").split(";")[0].strip().lower()
    aliases = {
        "image/jpg": "image/jpeg",
        "image/pjpeg": "image/jpeg",
        "image/x-png": "image/png",
    }
    mime = aliases.get(mime, mime)
    fn = (filename or "").lower()
    unknown = mime in ("", "application/octet-stream", "binary/octet-stream")
    if unknown or (mime not in ALLOWED_ATTACHMENT_MIME and fn):
        if fn.endswith(".png"):
            mime = "image/png"
        elif fn.endswith((".jpg", ".jpeg", ".jpe")):
            mime = "image/jpeg"
        elif fn.endswith(".gif"):
            mime = "image/gif"
        elif fn.endswith(".webp"):
            mime = "image/webp"
        elif fn.endswith(".pdf"):
            mime = "application/pdf"
    return mime


def connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def user_exists(username: str) -> bool:
    u = (username or "").strip()
    if not u:
        return False
    db = connect()
    cur = db.cursor()
    cur.execute("SELECT 1 FROM users WHERE username=?", (u,))
    ok = cur.fetchone() is not None
    db.close()
    return ok


def _pair(a: str, b: str) -> tuple[str, str]:
    x, y = a.strip(), b.strip()
    return (x, y) if x < y else (y, x)


def ensure_profile(username: str) -> None:
    db = connect()
    cur = db.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO user_profiles (username, display_name) VALUES (?, ?)",
        (username, username),
    )
    db.commit()
    db.close()


def ensure_global_room() -> int:
    """Return global room id (creates Market Chat if missing)."""
    db = connect()
    cur = db.cursor()
    cur.execute(
        "SELECT id FROM chat_rooms WHERE kind='global' LIMIT 1",
    )
    row = cur.fetchone()
    if row:
        rid = int(row[0])
        db.close()
        return rid
    cur.execute(
        """
        INSERT INTO chat_rooms (kind, name, created_by)
        VALUES ('global', ?, NULL)
        """,
        (GLOBAL_ROOM_NAME,),
    )
    rid = int(cur.lastrowid)
    db.commit()
    db.close()
    return rid


def get_global_room_id() -> int:
    return ensure_global_room()


def save_chat_attachment(
    content: bytes, mime: str, orig_filename: str = ""
) -> tuple[str | None, str]:
    """Write bytes to uploads/chat; return (storage_key, error_message). error_message is empty on success."""
    mime = _normalize_upload_mime(mime, orig_filename)
    if mime not in ALLOWED_ATTACHMENT_MIME:
        return None, "File type not allowed (JPEG, PNG, GIF, WebP, or PDF)."
    if not content or len(content) > MAX_ATTACHMENT_BYTES:
        return None, "File missing or too large (max 8 MB)."
    os.makedirs(CHAT_UPLOAD_DIR, exist_ok=True)
    ext = ALLOWED_ATTACHMENT_MIME[mime]
    key = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(CHAT_UPLOAD_DIR, key)
    with open(path, "wb") as f:
        f.write(content)
    return key, ""


def attachment_disk_path(storage_key: str) -> str | None:
    if not storage_key or ".." in storage_key or "/" in storage_key or "\\" in storage_key:
        return None
    if not all(c.isalnum() or c in "._-" for c in storage_key):
        return None
    path = os.path.join(CHAT_UPLOAD_DIR, storage_key)
    return path if os.path.isfile(path) else None


def get_message_attachment(
    message_id: int,
) -> tuple[int, str, str, str | None] | None:
    """Return (room_id, mime, absolute_path, orig_name) or None."""
    db = connect()
    cur = db.cursor()
    cur.execute(
        """
        SELECT room_id, attachment_storage, attachment_mime, attachment_orig_name
        FROM chat_messages WHERE id=?
        """,
        (message_id,),
    )
    row = cur.fetchone()
    db.close()
    if not row or not row[1]:
        return None
    rid, storage, mime, orig = int(row[0]), row[1], row[2] or "", row[3]
    path = attachment_disk_path(storage)
    if not path:
        return None
    return rid, mime, path, orig


# -------- Friends --------


def send_friend_request(from_user: str, to_user: str) -> tuple[bool, str]:
    a, b = from_user.strip(), to_user.strip()
    if not a or not b or a == b:
        return False, "Invalid usernames."
    if not user_exists(b):
        return False, "That user does not exist."
    ua, ub = _pair(a, b)
    db = connect()
    cur = db.cursor()
    cur.execute(
        "SELECT 1 FROM friends WHERE user_a=? AND user_b=?",
        (ua, ub),
    )
    if cur.fetchone():
        db.close()
        return False, "You are already friends."
    cur.execute(
        "SELECT id, status FROM friend_requests WHERE from_user=? AND to_user=?",
        (a, b),
    )
    row = cur.fetchone()
    if row:
        db.close()
        return False, "Request already sent."
    cur.execute(
        "SELECT id FROM friend_requests WHERE from_user=? AND to_user=?",
        (b, a),
    )
    if cur.fetchone():
        db.close()
        return False, "They already sent you a request — accept it in Social."
    cur.execute(
        """
        INSERT INTO friend_requests (from_user, to_user, status)
        VALUES (?, ?, 'pending')
        """,
        (a, b),
    )
    db.commit()
    db.close()
    return True, "ok"


def respond_friend_request(to_user: str, from_user: str, accept: bool) -> tuple[bool, str]:
    """to_user accepts or declines from_user's request."""
    db = connect()
    cur = db.cursor()
    cur.execute(
        """
        SELECT id FROM friend_requests
        WHERE from_user=? AND to_user=? AND status='pending'
        """,
        (from_user, to_user),
    )
    row = cur.fetchone()
    if not row:
        db.close()
        return False, "No pending request."
    cur.execute("DELETE FROM friend_requests WHERE id=?", (row[0],))
    if accept:
        ua, ub = _pair(from_user, to_user)
        cur.execute(
            "INSERT OR IGNORE INTO friends (user_a, user_b) VALUES (?, ?)",
            (ua, ub),
        )
    db.commit()
    db.close()
    return True, "ok"


def list_friends(username: str) -> list[str]:
    u = username.strip()
    db = connect()
    cur = db.cursor()
    cur.execute(
        """
        SELECT CASE WHEN user_a = ? THEN user_b ELSE user_a END
        FROM friends WHERE user_a = ? OR user_b = ?
        ORDER BY 1
        """,
        (u, u, u),
    )
    out = [r[0] for r in cur.fetchall()]
    db.close()
    return out


def are_friends(a: str, b: str) -> bool:
    if a == b:
        return True
    ua, ub = _pair(a, b)
    db = connect()
    cur = db.cursor()
    cur.execute(
        "SELECT 1 FROM friends WHERE user_a=? AND user_b=?",
        (ua, ub),
    )
    ok = cur.fetchone() is not None
    db.close()
    return ok


def list_incoming_requests(username: str) -> list[dict[str, Any]]:
    db = connect()
    cur = db.cursor()
    cur.execute(
        """
        SELECT from_user, created_at FROM friend_requests
        WHERE to_user=? AND status='pending'
        ORDER BY id DESC
        """,
        (username,),
    )
    rows = [{"from_user": r[0], "created_at": r[1]} for r in cur.fetchall()]
    db.close()
    return rows


def list_outgoing_requests(username: str) -> list[dict[str, Any]]:
    db = connect()
    cur = db.cursor()
    cur.execute(
        """
        SELECT to_user, created_at FROM friend_requests
        WHERE from_user=? AND status='pending'
        ORDER BY id DESC
        """,
        (username,),
    )
    rows = [{"to_user": r[0], "created_at": r[1]} for r in cur.fetchall()]
    db.close()
    return rows


# -------- Profiles --------


def get_profile(username: str) -> dict[str, Any]:
    ensure_profile(username)
    db = connect()
    cur = db.cursor()
    cur.execute(
        "SELECT username, display_name, bio, updated_at FROM user_profiles WHERE username=?",
        (username,),
    )
    row = cur.fetchone()
    db.close()
    if not row:
        return {
            "username": username,
            "display_name": username,
            "bio": "",
            "updated_at": None,
        }
    return {
        "username": row[0],
        "display_name": row[1] or row[0],
        "bio": row[2] or "",
        "updated_at": row[3],
    }


def update_profile(username: str, display_name: str | None, bio: str | None) -> dict[str, Any]:
    ensure_profile(username)
    dn = (display_name or "").strip()[:64] or username
    bio_s = (bio or "").strip()[:500]
    db = connect()
    cur = db.cursor()
    cur.execute(
        """
        UPDATE user_profiles SET display_name=?, bio=?, updated_at=CURRENT_TIMESTAMP
        WHERE username=?
        """,
        (dn, bio_s, username),
    )
    db.commit()
    db.close()
    return get_profile(username)


# -------- Rooms --------


def _room_row(room_id: int) -> dict[str, Any] | None:
    db = connect()
    cur = db.cursor()
    cur.execute(
        "SELECT id, kind, name, created_by, created_at FROM chat_rooms WHERE id=?",
        (room_id,),
    )
    row = cur.fetchone()
    db.close()
    if not row:
        return None
    return {
        "id": row[0],
        "kind": row[1],
        "name": row[2],
        "created_by": row[3],
        "created_at": row[4],
    }


def can_access_room(username: str, room_id: int) -> bool:
    r = _room_row(room_id)
    if not r:
        return False
    if r["kind"] == "global":
        return True
    db = connect()
    cur = db.cursor()
    cur.execute(
        "SELECT 1 FROM chat_members WHERE room_id=? AND username=?",
        (room_id, username),
    )
    ok = cur.fetchone() is not None
    db.close()
    return ok


def can_post_room(username: str, room_id: int) -> bool:
    return can_access_room(username, room_id)


def get_or_create_dm_room(a: str, b: str) -> tuple[int | None, str]:
    if not are_friends(a, b):
        return None, "Direct messages are only available between friends."
    if a == b:
        return None, "Invalid chat."
    db = connect()
    cur = db.cursor()
    cur.execute(
        """
        SELECT cr.id FROM chat_rooms cr
        INNER JOIN chat_members m1 ON m1.room_id = cr.id AND m1.username = ?
        INNER JOIN chat_members m2 ON m2.room_id = cr.id AND m2.username = ?
        WHERE cr.kind = 'dm'
        """,
        (a, b),
    )
    row = cur.fetchone()
    if row:
        rid = int(row[0])
        db.close()
        return rid, "ok"
    cur.execute(
        """
        INSERT INTO chat_rooms (kind, name, created_by)
        VALUES ('dm', NULL, ?)
        """,
        (a,),
    )
    rid = int(cur.lastrowid)
    cur.execute(
        "INSERT INTO chat_members (room_id, username, role) VALUES (?, ?, 'member')",
        (rid, a),
    )
    cur.execute(
        "INSERT INTO chat_members (room_id, username, role) VALUES (?, ?, 'member')",
        (rid, b),
    )
    db.commit()
    db.close()
    return rid, "ok"


def create_group_with_members(
    creator: str,
    name: str,
    member_usernames: list[str] | None,
) -> tuple[int | None, str]:
    """
    Trading group: creator is owner; member_usernames must already be friends.
    Empty members list is OK (invite more later).
    """
    member_usernames = member_usernames or []
    seen: set[str] = set()
    members: list[str] = []
    for raw in member_usernames:
        u = (raw or "").strip()
        if not u or u == creator or u in seen:
            continue
        seen.add(u)
        if not user_exists(u):
            return None, f"User not found: {u}"
        if not are_friends(creator, u):
            return None, f"Not friends with {u} — add them first, then create the group."
        members.append(u)
    if 1 + len(members) > MAX_GROUP_MEMBERS:
        return None, f"Too many members (max {MAX_GROUP_MEMBERS} including you)."
    nm = (name or "").strip()[:80]
    if len(nm) < 2:
        return None, "Group name must be at least 2 characters."
    db = connect()
    cur = db.cursor()
    try:
        cur.execute(
            """
            INSERT INTO chat_rooms (kind, name, created_by)
            VALUES ('group', ?, ?)
            """,
            (nm, creator),
        )
        rid = int(cur.lastrowid)
        cur.execute(
            "INSERT INTO chat_members (room_id, username, role) VALUES (?, ?, 'owner')",
            (rid, creator),
        )
        for u in members:
            cur.execute(
                "INSERT INTO chat_members (room_id, username, role) VALUES (?, ?, 'member')",
                (rid, u),
            )
        db.commit()
    except sqlite3.IntegrityError as e:
        db.rollback()
        db.close()
        return None, str(e) or "Could not create group."
    db.close()
    return rid, "ok"


def add_group_member(room_id: int, inviter: str, invitee: str) -> tuple[bool, str]:
    invitee = invitee.strip()
    if not user_exists(invitee):
        return False, "User does not exist."
    if not are_friends(inviter, invitee):
        return False, "You can only invite friends to a group."
    db = connect()
    cur = db.cursor()
    cur.execute(
        "SELECT kind FROM chat_rooms WHERE id=?",
        (room_id,),
    )
    row = cur.fetchone()
    if not row or row[0] != "group":
        db.close()
        return False, "Not a group room."
    cur.execute(
        "SELECT role FROM chat_members WHERE room_id=? AND username=?",
        (room_id, inviter),
    )
    mr = cur.fetchone()
    if not mr or mr[0] != "owner":
        db.close()
        return False, "Only the group owner can invite members."
    cur.execute("SELECT COUNT(*) FROM chat_members WHERE room_id=?", (room_id,))
    n = int(cur.fetchone()[0])
    if n >= MAX_GROUP_MEMBERS:
        db.close()
        return False, "Group is full."
    try:
        cur.execute(
            """
            INSERT INTO chat_members (room_id, username, role)
            VALUES (?, ?, 'member')
            """,
            (room_id, invitee),
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.close()
        return False, "Already in group."
    db.close()
    return True, "ok"


def list_user_rooms(username: str) -> list[dict[str, Any]]:
    """Rooms the user can open: global + memberships (DM + group)."""
    gid = get_global_room_id()
    db = connect()
    cur = db.cursor()
    cur.execute(
        """
        SELECT cr.id, cr.kind, cr.name, cr.created_by, m.role
        FROM chat_rooms cr
        INNER JOIN chat_members m ON m.room_id = cr.id AND m.username = ?
        WHERE cr.kind != 'global'
        ORDER BY cr.kind DESC, cr.name ASC
        """,
        (username,),
    )
    rows = cur.fetchall()
    member_rooms: list[dict[str, Any]] = []
    for row in rows:
        rid, kind, name, created_by, my_role = (
            int(row[0]),
            row[1],
            row[2],
            row[3],
            row[4],
        )
        label = name or "Direct message"
        if kind == "dm":
            cur.execute(
                """
                SELECT username FROM chat_members
                WHERE room_id=? AND username != ?
                LIMIT 1
                """,
                (rid, username),
            )
            other = cur.fetchone()
            label = f"DM · {other[0]}" if other else "Direct message"
        sub = ""
        if kind == "group":
            sub = "Friends-only trading room — share charts & screenshots."
        elif kind == "dm":
            sub = "Private — only you and your friend."
        member_rooms.append(
            {
                "id": rid,
                "kind": kind,
                "name": name,
                "label": label,
                "subtitle": sub,
                "created_by": created_by,
                "my_role": my_role,
                "msg_count": _message_count(rid),
            }
        )
    db.close()

    global_entry = {
        "id": gid,
        "kind": "global",
        "name": GLOBAL_ROOM_NAME,
        "label": "Live — " + GLOBAL_ROOM_NAME,
        "subtitle": GLOBAL_ROOM_SUBTITLE,
        "created_by": None,
        "my_role": None,
        "msg_count": _message_count(gid),
    }
    return [global_entry] + member_rooms


def _message_count(room_id: int) -> int:
    db = connect()
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM chat_messages WHERE room_id=?", (room_id,))
    n = int(cur.fetchone()[0])
    db.close()
    return n


# -------- Messages --------


def post_message(
    username: str,
    room_id: int,
    body: str,
    *,
    attachment_storage: str | None = None,
    attachment_mime: str | None = None,
    attachment_orig_name: str | None = None,
) -> tuple[bool, str, int | None]:
    text = (body or "").strip()
    if not text and not attachment_storage:
        return False, "Add text and/or attach an image or PDF.", None
    if text and len(text) > MAX_MESSAGE_LEN:
        return False, "Message too long.", None
    if not can_post_room(username, room_id):
        return False, "You cannot post in this room.", None
    if attachment_storage and not attachment_disk_path(attachment_storage):
        return False, "Attachment not found.", None
    store = attachment_storage if attachment_storage else None
    mime = (attachment_mime or "").split(";")[0].strip()[:120] if attachment_storage else None
    orig = (attachment_orig_name or "")[:200] if attachment_storage else None
    body_out = text if text else ""
    db = connect()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO chat_messages (room_id, username, body, attachment_storage, attachment_mime, attachment_orig_name)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (room_id, username, body_out, store, mime, orig),
    )
    mid = int(cur.lastrowid)
    db.commit()
    db.close()
    return True, "ok", mid


def list_messages(
    room_id: int,
    username: str,
    *,
    after_id: int | None = None,
    limit: int = 80,
) -> tuple[list[dict[str, Any]], str | None]:
    if not can_access_room(username, room_id):
        return [], "Forbidden"
    lim = max(1, min(limit, 200))
    db = connect()
    cur = db.cursor()
    sel = """
        SELECT id, username, body, created_at,
               attachment_storage, attachment_mime, attachment_orig_name
        FROM chat_messages
    """
    if after_id is not None and after_id > 0:
        cur.execute(
            sel
            + """
            WHERE room_id=? AND id > ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (room_id, after_id, lim),
        )
    else:
        cur.execute(
            sel
            + """
            WHERE room_id=?
            ORDER BY id DESC
            LIMIT ?
            """,
            (room_id, lim),
        )
    rows = cur.fetchall()
    db.close()
    msgs = []
    for r in reversed(rows):
        att_storage = r[4] if len(r) > 4 else None
        att_mime = r[5] if len(r) > 5 else None
        att_orig = r[6] if len(r) > 6 else None
        m: dict[str, Any] = {
            "id": r[0],
            "username": r[1],
            "body": r[2],
            "created_at": r[3],
        }
        if att_storage:
            m["attachment"] = {
                "mime": att_mime or "application/octet-stream",
                "url": f"/api/social/media/{r[0]}",
                "filename": att_orig or "attachment",
            }
        msgs.append(m)
    return msgs, None
