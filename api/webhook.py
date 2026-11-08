"""
Amarseba SMS Telegram Bot — Vercel
SMS History + Bot ON/OFF + User tracking + Edit-in-place storage
"""
import time
import json
import uuid
import traceback
from datetime import datetime, timezone, timedelta
import requests
import cloudscraper
from flask import Flask, request, jsonify

# ==================== CONFIG ====================
TELEGRAM_BOT_TOKEN = "8896805760:AAFYDVaKzleuPINa0AjlBSsrbBR8IytO3S0"
AMARSEBA_API_KEY_DEFAULT = "sk-ams-live-Xqoc4Aley0GyV8XbzXjZCdReeePqOrpYSjNP0Cc5k8pnFLLh"
AMARSEBA_BASE_URL = "https://e-amarseba.com/api/v1"

ADMIN_CHAT_IDS = ["6552783238", "1700797877"]

# 🔒 Optional: hidden storage channel
STORAGE_CHAT_ID = "-1004350390541"   # e.g., "-1001234567890"

STORE_PREFIX = "🔑AMARSEBA_STATE::"
LEGACY_KEY_PREFIX = "🔑AMARSEBA_KEY::"

# Storage limits (fitted automatically to fit pinned message)
MAX_USERS_INLINE = 100
MAX_HISTORY = 30
MAX_PINNED_CHARS = 3800

# Timezone for display
BD_TZ = timezone(timedelta(hours=6))

DEV_NAME = "SHAKIB"
DEV_LINK = "https://t.me/shakib2016"
BOT_NAME = "SAKIB CUSTOM SMS BOT"
SEP = "━━━━━━━━━━━━━━━━━━━━━━━━"
# ================================================

app = Flask(__name__)

scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "desktop": True}
)

_memory_state = {
    "api_key": None,
    "bot_on": True,
    "users": {},
    "user_count": 0,
    "history": [],
    "state_message_id": None,
}


# ============================================================
# STORAGE
# ============================================================
def _storage_chat():
    if STORAGE_CHAT_ID:
        return STORAGE_CHAT_ID
    return ADMIN_CHAT_IDS[0] if ADMIN_CHAT_IDS else None


def _get_pinned():
    chat = _storage_chat()
    if not chat:
        return None, ""
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getChat",
            params={"chat_id": chat}, timeout=10,
        )
        j = r.json()
        pinned = (j.get("result") or {}).get("pinned_message") or {}
        return pinned.get("message_id"), (pinned.get("text", "") or "")
    except Exception as e:
        print(f"_get_pinned error: {e}")
        return None, ""


def state_read():
    _, text = _get_pinned()
    if not text:
        return None
    if text.startswith(STORE_PREFIX):
        try:
            data = json.loads(text[len(STORE_PREFIX):])
        except Exception:
            data = {}
        return {
            "api_key": data.get("api_key") or None,
            "bot_on": bool(data.get("bot_on", True)),
            "users": data.get("users") or {},
            "user_count": int(data.get("user_count", 0) or 0),
            "history": data.get("history") or [],
        }
    if text.startswith(LEGACY_KEY_PREFIX):
        k = text[len(LEGACY_KEY_PREFIX):].strip()
        return {
            "api_key": (k or None),
            "bot_on": True,
            "users": {},
            "user_count": 0,
            "history": [],
        }
    return None


def _build_payload(state):
    """Trim users & history to fit pinned message."""
    users = dict(state.get("users") or {})
    history = list(state.get("history") or [])

    for max_h, max_u in [
        (MAX_HISTORY, MAX_USERS_INLINE),
        (20, 80), (15, 60), (10, 40), (7, 30), (5, 20), (3, 10),
    ]:
        if len(history) > max_h:
            history = history[-max_h:]
        if len(users) > max_u:
            items = sorted(users.items(), key=lambda kv: kv[1])
            users = dict(items[-max_u:])

        payload = {
            "api_key": state.get("api_key") or "",
            "bot_on": bool(state.get("bot_on", True)),
            "user_count": int(state.get("user_count", 0) or 0),
            "users": users,
            "history": history,
        }
        txt = f"{STORE_PREFIX}{json.dumps(payload, separators=(',', ':'))}"
        if len(txt) <= MAX_PINNED_CHARS:
            return payload

    return payload


def state_write(state):
    chat = _storage_chat()
    if not chat:
        return False

    payload = _build_payload(state)
    new_text = f"{STORE_PREFIX}{json.dumps(payload, separators=(',', ':'))}"

    existing_id, existing_text = _get_pinned()

    if existing_id and (existing_text or "").startswith(STORE_PREFIX):
        try:
            er = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText",
                json={
                    "chat_id": chat,
                    "message_id": existing_id,
                    "text": new_text,
                }, timeout=15,
            )
            j = er.json()
            if j.get("ok"):
                _memory_state["state_message_id"] = existing_id
                return True
            if "not modified" in j.get("description", ""):
                return True
        except Exception as e:
            print(f"state_write edit error: {e}")

    # Fallback: delete + send new + pin
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/unpinAllChatMessages",
            json={"chat_id": chat}, timeout=10,
        )
    except Exception:
        pass
    if existing_id:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteMessage",
                json={"chat_id": chat, "message_id": existing_id}, timeout=10,
            )
        except Exception:
            pass

    r = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={
            "chat_id": chat,
            "text": new_text,
            "disable_notification": True,
        }, timeout=15,
    )
    j = r.json()
    if not j.get("ok"):
        return False
    new_id = j["result"]["message_id"]
    pr = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/pinChatMessage",
        json={
            "chat_id": chat,
            "message_id": new_id,
            "disable_notification": True,
        }, timeout=15,
    )
    _memory_state["state_message_id"] = new_id
    return pr.json().get("ok", False)


# ============================================================
# STATE HELPERS
# ============================================================
def _current_state():
    st = state_read()
    if st is not None:
        return st
    return {
        "api_key": _memory_state["api_key"],
        "bot_on": _memory_state["bot_on"],
        "users": _memory_state["users"],
        "user_count": _memory_state["user_count"],
        "history": _memory_state["history"],
    }


def get_api_key():
    return _current_state().get("api_key") or AMARSEBA_API_KEY_DEFAULT


def is_bot_on():
    return bool(_current_state().get("bot_on", True))


def set_api_key(new_key):
    st = _current_state()
    st["api_key"] = new_key
    _memory_state["api_key"] = new_key
    return "blob" if state_write(st) else "memory"


def clear_api_key():
    st = _current_state()
    st["api_key"] = ""
    _memory_state["api_key"] = None
    state_write(st)


def set_bot_on(value):
    st = _current_state()
    st["bot_on"] = bool(value)
    _memory_state["bot_on"] = bool(value)
    return state_write(st)


def track_user(chat_id):
    st = _current_state()
    users = dict(st.get("users") or {})
    key = str(chat_id)
    if key in users:
        return False
    if len(users) >= MAX_USERS_INLINE:
        return False
    users[key] = datetime.now(BD_TZ).strftime("%Y-%m-%d")
    st["users"] = users
    st["user_count"] = int(st.get("user_count", 0) or 0) + 1
    _memory_state["users"] = users
    _memory_state["user_count"] = st["user_count"]
    state_write(st)
    return True


def get_user_stats():
    st = _current_state()
    return {
        "count": int(st.get("user_count", 0) or 0),
        "users": st.get("users") or {},
    }


def reset_users():
    st = _current_state()
    st["users"] = {}
    st["user_count"] = 0
    _memory_state["users"] = {}
    _memory_state["user_count"] = 0
    return state_write(st)


# ============================================================
# SMS HISTORY
# ============================================================
def add_history(chat_id, phone, body, cost, status="processing"):
    st = _current_state()
    hist = list(st.get("history") or [])
    now = datetime.now(BD_TZ)

    record = {
        "t": now.strftime("%m-%d %H:%M"),
        "u": str(chat_id),
        "p": phone,
        "m": (body or "")[:40],
        "c": str(cost) if cost is not None else "-",
        "s": status,
    }
    hist.append(record)
    if len(hist) > MAX_HISTORY:
        hist = hist[-MAX_HISTORY:]

    st["history"] = hist
    _memory_state["history"] = hist
    state_write(st)
    return record


def update_history_status(chat_id, phone, final_status):
    st = _current_state()
    hist = list(st.get("history") or [])
    for i in range(len(hist) - 1, -1, -1):
        r = hist[i]
        if r.get("u") == str(chat_id) and r.get("p") == phone:
            r["s"] = final_status
            st["history"] = hist
            _memory_state["history"] = hist
            state_write(st)
            return True
    return False


def clear_history():
    st = _current_state()
    st["history"] = []
    _memory_state["history"] = []
    return state_write(st)


def get_history(chat_id=None):
    st = _current_state()
    hist = list(st.get("history") or [])
    if chat_id is not None:
        hist = [r for r in hist if r.get("u") == str(chat_id)]
    return hist


def is_admin(chat_id):
    return str(chat_id) in ADMIN_CHAT_IDS


def get_headers():
    return {
        "Authorization": f"Bearer {get_api_key()}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def mask_key(k):
    if not k or len(k) < 16:
        return "***"
    return f"{k[:12]}...{k[-4:]}"


# ============================================================
# TELEGRAM HELPERS
# ============================================================
def tg_api(method, payload, timeout=20):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}",
            json=payload, timeout=timeout,
        )
        return r.json()
    except Exception as e:
        print(f"tg_api {method} error: {e}")
        return {"ok": False}


def tg_send(chat_id, text, reply_markup=None, parse_mode="HTML"):
    payload = {
        "chat_id": chat_id, "text": text, "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return tg_api("sendMessage", payload)


def tg_send_id(chat_id, text, reply_markup=None, parse_mode="HTML"):
    j = tg_send(chat_id, text, reply_markup, parse_mode)
    return j["result"]["message_id"] if j.get("ok") else None


def tg_edit(chat_id, message_id, text, reply_markup=None, parse_mode="HTML"):
    payload = {
        "chat_id": chat_id, "message_id": message_id,
        "text": text, "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return tg_api("editMessageText", payload)


def tg_typing(chat_id):
    tg_api("sendChatAction", {"chat_id": chat_id, "action": "typing"}, timeout=10)


def tg_answer_cb(cq_id, text=None, show_alert=False):
    payload = {"callback_query_id": cq_id}
    if text:
        payload["text"] = text
        payload["show_alert"] = show_alert
    return tg_api("answerCallbackQuery", payload, timeout=10)


# ============================================================
# KEYBOARDS
# ============================================================
def kb_main():
    return {"inline_keyboard": [
        [{"text": "💰 Balance", "callback_data": "balance"},
         {"text": "📖 Help", "callback_data": "help"}],
        [{"text": "📝 History", "callback_data": "history"},
         {"text": "👨‍💻 Developer", "url": DEV_LINK}],
    ]}


def kb_help():
    return {"inline_keyboard": [
        [{"text": "💰 Balance", "callback_data": "balance"},
         {"text": "🏠 Home", "callback_data": "home"}],
        [{"text": "📝 History", "callback_data": "history"},
         {"text": "👨‍💻 Developer", "url": DEV_LINK}],
    ]}


def kb_balance():
    return {"inline_keyboard": [
        [{"text": "🔄 Refresh", "callback_data": "balance"},
         {"text": "📖 Help", "callback_data": "help"}],
        [{"text": "📝 History", "callback_data": "history"},
         {"text": "🏠 Home", "callback_data": "home"}],
        [{"text": "👨‍💻 Developer", "url": DEV_LINK}],
    ]}


def kb_admin():
    return {"inline_keyboard": [
        [{"text": "💰 Balance", "callback_data": "balance"},
         {"text": "🔍 Debug", "callback_data": "debug"}],
        [{"text": "📊 Users", "callback_data": "users"},
         {"text": "📝 History", "callback_data": "history"}],
        [{"text": "📖 Help", "callback_data": "help"},
         {"text": "👨‍💻 Developer", "url": DEV_LINK}],
    ]}


def kb_sms():
    return {"inline_keyboard": [
        [{"text": "🏠 Home", "callback_data": "home"},
         {"text": "💰 Balance", "callback_data": "balance"}],
        [{"text": "📝 History", "callback_data": "history"},
         {"text": "📖 Help", "callback_data": "help"}],
        [{"text": "👨‍💻 Developer", "url": DEV_LINK}],
    ]}


def kb_history(is_admin_user):
    if is_admin_user:
        return {"inline_keyboard": [
            [{"text": "🔄 Refresh", "callback_data": "history"},
             {"text": "🗑️ Clear All", "callback_data": "clearhistory"}],
            [{"text": "🏠 Home", "callback_data": "home"},
             {"text": "👨‍💻 Developer", "url": DEV_LINK}],
        ]}
    return {"inline_keyboard": [
        [{"text": "🔄 Refresh", "callback_data": "history"},
         {"text": "🏠 Home", "callback_data": "home"}],
        [{"text": "👨‍💻 Developer", "url": DEV_LINK}],
    ]}


# ============================================================
# MESSAGES
# ============================================================
def msg_welcome(chat_id):
    is_adm = is_admin(chat_id)
    body = (
        f"╔══════════════════════════╗\n"
        f"   🤖 <b>{BOT_NAME}</b> 🤖\n"
        f"╚══════════════════════════╝\n\n"
        f"✨ <i>Fast · Secure · Easy</i> ✨\n\n"
        f"{SEP}\n\n"
        f"📤 <b>How to Send SMS</b>\n\n"
        f"<code>01712345678 your message</code>\n\n"
        f"💡 <b>Examples:</b>\n"
        f"<code>01712345678 Hello</code>\n"
        f"<code>01712345678 Your message</code>\n\n"
        f"{SEP}\n"
    )
    if is_adm:
        body += (
            f"\n👑 <b>Admin Commands:</b>\n"
            f"  • /setkey — Set API key\n"
            f"  • /delkey — Delete key\n"
            f"  • /debug — System test\n"
            f"  • /botoff / /boton — Toggle bot\n"
            f"  • /botstatus — Bot state\n"
            f"  • /users — Total users\n"
            f"  • /history — SMS history\n"
            f"  • /clearhistory — Reset history\n"
            f"  • /cleanstate — Cleanup state\n\n"
            f"{SEP}\n"
        )
    else:
        body += (
            f"\n📋 <b>Commands:</b>\n"
            f"  • /balance — Wallet balance\n"
            f"  • /history — Your SMS history\n"
            f"  • /id — Your chat ID\n"
            f"  • /help — Detailed guide\n\n"
            f"{SEP}\n"
        )
    body += f"\n👨‍💻 <b>Developer:</b> <a href=\"{DEV_LINK}\">@shakib2016</a>"
    return body


def msg_help(chat_id):
    return (
        f"📖 <b>Detailed Guide</b>\n\n"
        f"{SEP}\n\n"
        f"1️⃣ <b>How to Send SMS</b>\n\n"
        f"Write in this format:\n"
        f"<code>01XXXXXXXXX your message</code>\n\n"
        f"✅ <b>Correct Examples:</b>\n"
        f"<code>01712345678 Hello</code>\n"
        f"<code>01712345678 Your message</code>\n\n"
        f"❌ <b>Wrong Example:</b>\n"
        f"<code>Hello 01712345678</code> (number first)\n\n"
        f"{SEP}\n\n"
        f"❓ <b>Having Problems?</b>\n\n"
        f"Contact the developer:\n"
        f"👉 <a href=\"{DEV_LINK}\">@shakib2016</a>"
    )


def msg_balance(d):
    return (
        f"💰 <b>Wallet Balance</b>\n\n"
        f"┏━━━━━━━━━━━━━━━━━━━┓\n"
        f"     💵 <b>{d.get('balance')} {d.get('currency')}</b>\n"
        f"┗━━━━━━━━━━━━━━━━━━━┛\n\n"
        f"📌 Status: <b>{d.get('status', 'active').upper()}</b>\n"
        f"⏰ <i>Real-time data</i>\n\n"
        f"{SEP}"
    )


def msg_processing():
    return f"⏳ <b>Processing...</b>\n\n{SEP}\n\nPlease wait..."


def status_display(st):
    s = str(st or "").lower()
    if s in ("sent", "delivered", "success"):
        return "✅", "Sent"
    if s == "failed":
        return "❌", "Failed"
    if s == "refunded":
        return "💸", "Refunded"
    if s == "queued":
        return "⏳", "Queued"
    return "⏳", "Processing"


def msg_sms(phone, status="processing", cost=None, balance_after=None):
    emoji, label = status_display(status)
    lines = [
        f"📨 <b>SMS Details</b>\n",
        f"┏━━━━━━━━━━━━━━━━━━━┓",
        f"   📋 <b>Info</b>",
        f"┗━━━━━━━━━━━━━━━━━━━┛\n",
        f"📱 Recipient: <code>{phone}</code>",
        f"📊 Status: {emoji} <b>{label}</b>",
    ]
    if cost is not None:
        lines.append(f"💵 Cost: <b>{cost} BDT</b>")
    if balance_after is not None:
        lines.append(f"💰 New Balance: <b>{balance_after} BDT</b>")
    lines += ["", SEP]
    return "\n".join(lines)


def msg_error(status, data):
    msg = data.get("message", "Unknown error") if isinstance(data, dict) else str(data)
    return (
        f"❌ <b>Error Occurred</b>\n\n{SEP}\n\n"
        f"📊 HTTP: <code>{status}</code>\n"
        f"💬 Message: <code>{msg[:200]}</code>\n\n"
        f"{SEP}\n\n"
        f"🔧 Solution:\n"
        f"  • Check if number is correct\n"
        f"  • Check balance (/balance)\n"
        f"  • Try again\n\n"
        f"❓ Need help: @shakib2016"
    )


def msg_debug(chat_id, d, src):
    st = state_read() or {}
    storage_hidden = "🔒 Hidden" if STORAGE_CHAT_ID else "⚠️ Visible"
    bot_state = "🟢 ON" if is_bot_on() else "🔴 OFF"
    return (
        f"🔍 <b>System Status</b>\n\n"
        f"┏━━━━━━━━━━━━━━━━━━━┓\n"
        f"   💰 <b>{d.get('balance')} {d.get('currency')}</b>\n"
        f"┗━━━━━━━━━━━━━━━━━━━┛\n\n"
        f"📌 Status: <b>{d.get('status', 'active').upper()}</b>\n"
        f"🤖 Bot: <b>{bot_state}</b>\n"
        f"👥 Users: <b>{int(st.get('user_count', 0) or 0)}</b>\n"
        f"📝 History: <b>{len(st.get('history') or [])}</b>\n"
        f"🔑 Key: <code>{mask_key(get_api_key())}</code>\n"
        f"📦 Source: <b>{src}</b>\n"
        f"🗄️ Storage: {storage_hidden}\n"
        f"👑 Admin: {'✅ Yes' if is_admin(chat_id) else '❌ No'}\n\n"
        f"{SEP}"
    )


def msg_bot_off():
    return (
        f"🔴 <b>Bot is Currently OFF</b>\n\n{SEP}\n\n"
        f"⚠️ Temporarily disabled by admin.\n\n"
        f"🕐 Please try again later.\n\n{SEP}\n\n"
        f"👨‍💻 <b>Need help?</b>\n"
        f"👉 <a href=\"{DEV_LINK}\">@shakib2016</a>"
    )


def msg_bot_toggled(is_on, persisted):
    icon = "🟢" if is_on else "🔴"
    state = "ON" if is_on else "OFF"
    note = "🔒 Persists across cold starts" if persisted else "⚠️ Memory only"
    desc = (
        "Users can now use the bot normally."
        if is_on
        else "Non-admin users will see \"Bot is OFF\" message."
    )
    return f"{icon} <b>Bot is Now {state}</b>\n\n{SEP}\n\n{desc}\n\n{note}\n\n{SEP}"


def msg_users():
    stats = get_user_stats()
    users = stats["users"]
    recent = list(users.keys())[-10:]
    lines = [f"👥 <b>Bot Users</b>\n", f"{SEP}\n", f"📊 <b>Total:</b> <b>{stats['count']}</b>\n"]
    if recent:
        lines.append(f"\n🆕 <b>Recent ({len(recent)}):</b>")
        for uid in reversed(recent):
            lines.append(f"  • <code>{uid}</code> — {users.get(uid, '')}")
    else:
        lines.append("\n<i>No users tracked yet.</i>")
    lines += [f"\n{SEP}", f"💡 Reset: /resetusers"]
    return "\n".join(lines)


def msg_history(chat_id, is_admin_user):
    hist = get_history(None if is_admin_user else chat_id)

    if not hist:
        return (
            f"📝 <b>SMS History</b>\n\n{SEP}\n\n"
            f"<i>No SMS sent yet.</i>\n\n"
            f"💡 Send one like:\n"
            f"<code>01712345678 Hello</code>\n\n{SEP}"
        )

    total_count = len(hist)
    total_cost = 0.0
    for r in hist:
        try:
            if r.get("c") and r.get("c") != "-":
                total_cost += float(r["c"])
        except Exception:
            pass

    lines = [
        f"📝 <b>SMS History</b>",
        f"",
        f"{SEP}",
        f"",
        f"📊 Total: <b>{total_count}</b> SMS | <b>{total_cost:.2f} BDT</b>",
        f"",
        f"{SEP}",
        f"",
    ]

    # Show last 10
    display = hist[-10:]
    for r in reversed(display):
        s = str(r.get("s", "")).lower()
        if s == "sent" or s == "delivered":
            icon = "✅"
        elif s == "failed":
            icon = "❌"
        elif s == "refunded":
            icon = "💸"
        elif s == "queued":
            icon = "⏳"
        else:
            icon = "⏳"

        t = r.get("t", "??")
        phone = r.get("p", "-")
        cost = r.get("c", "-")
        body_preview = r.get("m", "")

        lines.append(f"🕐 <b>{t}</b>   {icon}")
        lines.append(f"📱 <code>{phone}</code>  💵 <b>{cost} BDT</b>")
        if is_admin_user:
            lines.append(f"👤 <code>{r.get('u', '-')}</code>")
        if body_preview:
            lines.append(f"💬 <i>{body_preview}</i>")
        lines.append("")

    lines.append(SEP)
    if total_count > 10:
        lines.append(f"<i>Showing last 10 of {total_count}</i>")
    return "\n".join(lines).strip()


# ============================================================
# AMARSEBA API
# ============================================================
def amarseba_send(phone, body):
    h = get_headers()
    h["Idempotency-Key"] = str(uuid.uuid4())
    try:
        r = scraper.post(
            f"{AMARSEBA_BASE_URL}/bulk-sms/send",
            headers=h, json={"to": phone, "body": body}, timeout=50,
        )
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, {"success": False, "message": r.text[:300]}
    except Exception as e:
        return 0, {"success": False, "message": str(e)}


def amarseba_balance():
    try:
        r = scraper.get(
            f"{AMARSEBA_BASE_URL}/wallet/balance",
            headers=get_headers(), timeout=20,
        )
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, {"success": False, "message": r.text[:300]}
    except Exception as e:
        return 0, {"success": False, "message": str(e)}


def amarseba_batch(batch_id):
    try:
        r = scraper.get(
            f"{AMARSEBA_BASE_URL}/bulk-sms/batches/{batch_id}",
            headers=get_headers(), timeout=12,
        )
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, {"success": False}
    except Exception as e:
        return 0, {"success": False, "message": str(e)}


def extract_status(bd):
    if not isinstance(bd, dict):
        return None
    st = bd.get("status")
    if st:
        return str(st).lower()
    counts = bd.get("counts") or {}
    if isinstance(counts, dict) and counts:
        def _i(k):
            try:
                return int(counts.get(k, 0))
            except Exception:
                return 0
        sent, failed, queued, sending = _i("sent"), _i("failed"), _i("queued"), _i("sending")
        total = sent + failed + queued + sending
        if total > 0:
            if sent + failed >= total:
                return "sent" if sent > 0 else "failed"
            if sending > 0 or sent > 0:
                return "sending"
    return None


def is_valid_phone(p):
    c = p.replace("+", "").replace("-", "").replace(" ", "")
    return c.isdigit() and 10 <= len(c) <= 14


# ============================================================
# COMMANDS
# ============================================================
def cmd_start(chat_id):
    kb = kb_admin() if is_admin(chat_id) else kb_main()
    tg_send(chat_id, msg_welcome(chat_id), reply_markup=kb)


def cmd_help(chat_id):
    tg_send(chat_id, msg_help(chat_id), reply_markup=kb_help())


def cmd_id(chat_id):
    tg_send(chat_id,
        f"🆔 <b>Your Chat ID</b>\n\n{SEP}\n\n<code>{chat_id}</code>\n\n{SEP}\n\n"
        f"💡 Copy and send to the developer",
        reply_markup=kb_main())


def cmd_balance(chat_id):
    tg_typing(chat_id)
    pid = tg_send_id(chat_id, msg_processing())
    status, data = amarseba_balance()
    if status == 200 and data.get("success"):
        txt = msg_balance(data["data"])
        kb = kb_balance()
    else:
        txt = msg_error(status, data)
        kb = kb_main()
    if pid:
        tg_edit(chat_id, pid, txt, reply_markup=kb)
    else:
        tg_send(chat_id, txt, reply_markup=kb)


def cmd_history(chat_id):
    is_adm = is_admin(chat_id)
    txt = msg_history(chat_id, is_adm)
    tg_send(chat_id, txt, reply_markup=kb_history(is_adm))


def cmd_clearhistory(chat_id):
    if not is_admin(chat_id):
        tg_send(chat_id, "🔒 Admin only", reply_markup=kb_main())
        return
    ok = clear_history()
    if ok:
        tg_send(chat_id,
            f"🗑️ <b>History Cleared</b>\n\n{SEP}\n\n"
            f"✅ All SMS records deleted\n\n"
            f"<i>Next SMS will start a new history.</i>",
            reply_markup=kb_admin())
    else:
        tg_send(chat_id, f"❌ Failed to clear history.")


def cmd_debug(chat_id):
    if not is_admin(chat_id):
        tg_send(chat_id, f"🔒 <b>Admin-only</b>\n\n{SEP}\n\n📖 /help\n💡 /id",
                reply_markup=kb_main())
        return
    tg_typing(chat_id)
    pid = tg_send_id(chat_id, msg_processing())
    status, data = amarseba_balance()
    if status == 200 and data.get("success"):
        st = state_read()
        src = "telegram_pin" if (st and st.get("api_key")) else (
            "memory" if _memory_state["api_key"] else "default"
        )
        txt = msg_debug(chat_id, data["data"], src)
        kb = kb_admin()
    else:
        txt = msg_error(status, data)
        kb = kb_admin()
    if pid:
        tg_edit(chat_id, pid, txt, reply_markup=kb)
    else:
        tg_send(chat_id, txt, reply_markup=kb)


def cmd_setkey(chat_id, new_key):
    if not is_admin(chat_id):
        tg_send(chat_id, f"🔒 <b>Admin only</b>\n\n🆔 <code>{chat_id}</code>",
                reply_markup=kb_main())
        return
    if not new_key:
        tg_send(chat_id, f"📝 <b>Usage</b>\n\n<code>/setkey sk-ams-live-...</code>")
        return
    if not new_key.startswith("sk-ams-"):
        tg_send(chat_id, f"❌ Key must start with <code>sk-ams-</code>")
        return
    pid = tg_send_id(chat_id, "⏳ Saving...")
    where = set_api_key(new_key)
    if where == "blob":
        txt = (f"✅ <b>API key saved</b>\n\n{SEP}\n\n"
               f"🔑 <code>{mask_key(new_key)}</code>\n\n"
               f"🔒 Persists across cold starts")
    else:
        txt = (f"⚠️ <b>Memory only</b>\n\n{SEP}\n\n"
               f"🔑 <code>{mask_key(new_key)}</code>")
    if pid:
        tg_edit(chat_id, pid, txt)
    else:
        tg_send(chat_id, txt)


def cmd_delkey(chat_id):
    if not is_admin(chat_id):
        tg_send(chat_id, "🔒 Admin only", reply_markup=kb_main())
        return
    clear_api_key()
    tg_send(chat_id, f"🗑️ <b>Key deleted</b>\n\nNow using default")


def cmd_botoff(chat_id):
    if not is_admin(chat_id):
        tg_send(chat_id, "🔒 Admin only", reply_markup=kb_main())
        return
    p = set_bot_on(False)
    tg_send(chat_id, msg_bot_toggled(False, p), reply_markup=kb_admin())


def cmd_boton(chat_id):
    if not is_admin(chat_id):
        tg_send(chat_id, "🔒 Admin only", reply_markup=kb_main())
        return
    p = set_bot_on(True)
    tg_send(chat_id, msg_bot_toggled(True, p), reply_markup=kb_admin())


def cmd_botstatus(chat_id):
    if not is_admin(chat_id):
        tg_send(chat_id, "🔒 Admin only", reply_markup=kb_main())
        return
    on = is_bot_on()
    icon, state = ("🟢", "ON") if on else ("🔴", "OFF")
    tg_send(chat_id,
        f"{icon} <b>Bot Status: {state}</b>\n\n{SEP}\n\n"
        f"💡 Toggle: /botoff or /boton",
        reply_markup=kb_admin())


def cmd_users(chat_id):
    if not is_admin(chat_id):
        tg_send(chat_id, "🔒 Admin only", reply_markup=kb_main())
        return
    tg_send(chat_id, msg_users(), reply_markup=kb_admin())


def cmd_resetusers(chat_id):
    if not is_admin(chat_id):
        tg_send(chat_id, "🔒 Admin only", reply_markup=kb_main())
        return
    ok = reset_users()
    tg_send(chat_id, f"🗑️ <b>Users reset</b>" if ok else "❌ Failed")


def cmd_cleanstate(chat_id):
    if not is_admin(chat_id):
        tg_send(chat_id, "🔒 Admin only", reply_markup=kb_main())
        return
    storage = _storage_chat()
    if not storage:
        tg_send(chat_id, "❌ No storage chat")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/unpinAllChatMessages",
            json={"chat_id": storage}, timeout=10,
        )
    except Exception:
        pass
    mid, mtext = _get_pinned()
    if mid and (mtext or "").startswith(STORE_PREFIX):
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteMessage",
                json={"chat_id": storage, "message_id": mid}, timeout=10,
            )
        except Exception:
            pass
    _memory_state["state_message_id"] = None
    tg_send(chat_id,
        f"🧹 <b>Cleanup done</b>\n\n{SEP}\n\n"
        f"✅ Unpinned and deleted current state\n"
        f"⚠️ Old messages may need manual deletion",
        reply_markup=kb_admin())


def cmd_send_sms(chat_id, phone, body):
    if not is_valid_phone(phone):
        tg_send(chat_id, f"❌ <b>Invalid phone</b>\n\n<code>01712345678 your message</code>",
                reply_markup=kb_main())
        return
    if not body:
        tg_send(chat_id, "❌ Message is empty", reply_markup=kb_main())
        return

    tg_typing(chat_id)
    pid = tg_send_id(chat_id, msg_processing())

    status, data = amarseba_send(phone, body)
    if not (status in (200, 201, 202) and data.get("success")):
        txt = msg_error(status, data)
        kb = kb_main()
        if pid:
            tg_edit(chat_id, pid, txt, reply_markup=kb)
        else:
            tg_send(chat_id, txt, reply_markup=kb)
        return

    d = data.get("data", {}) or {}
    batch_id = d.get("batch_id", "")
    cost = d.get("total_cost")
    bal = d.get("balance_after")

    # Add history entry (queued)
    add_history(chat_id, phone, body, cost, status="queued")

    proc_txt = msg_sms(phone, "processing", cost, bal)
    if pid:
        tg_edit(chat_id, pid, proc_txt, reply_markup=kb_sms())
    else:
        pid = tg_send_id(chat_id, proc_txt, reply_markup=kb_sms())

    final = "sent"
    if batch_id:
        try:
            time.sleep(1.5)
            sc, sr = amarseba_batch(batch_id)
            if sc == 200 and sr.get("success"):
                ext = extract_status(sr.get("data", {}) or {})
                if str(ext).lower() == "failed":
                    final = "failed"
        except Exception as e:
            print(f"batch check error: {e}")

    # Update history with final status
    update_history_status(chat_id, phone, final)

    final_txt = msg_sms(phone, final, cost, bal)
    if pid:
        tg_edit(chat_id, pid, final_txt, reply_markup=kb_sms())
    else:
        tg_send(chat_id, final_txt, reply_markup=kb_sms())


# ============================================================
# CALLBACK
# ============================================================
def handle_callback(cq):
    try:
        cq_id = cq["id"]
        chat_id = cq["message"]["chat"]["id"]
        mid = cq["message"]["message_id"]
        data = cq.get("data", "")

        if not is_admin(chat_id) and not is_bot_on():
            tg_answer_cb(cq_id, "🔴 Bot is OFF", show_alert=True)
            return

        tg_answer_cb(cq_id)

        if data == "balance":
            tg_typing(chat_id)
            tg_edit(chat_id, mid, msg_processing())
            status, resp = amarseba_balance()
            if status == 200 and resp.get("success"):
                tg_edit(chat_id, mid, msg_balance(resp["data"]), kb_balance())
            else:
                tg_edit(chat_id, mid, msg_error(status, resp), kb_main())

        elif data == "help":
            tg_edit(chat_id, mid, msg_help(chat_id), kb_help())

        elif data == "home":
            kb = kb_admin() if is_admin(chat_id) else kb_main()
            tg_edit(chat_id, mid, msg_welcome(chat_id), kb)

        elif data == "history":
            is_adm = is_admin(chat_id)
            tg_edit(chat_id, mid, msg_history(chat_id, is_adm), kb_history(is_adm))

        elif data == "clearhistory":
            if not is_admin(chat_id):
                tg_answer_cb(cq_id, "🔒 Admin only", show_alert=True)
                return
            clear_history()
            tg_edit(chat_id, mid,
                f"🗑️ <b>History Cleared</b>\n\n{SEP}\n\n"
                f"✅ All SMS records deleted",
                kb_history(True))

        elif data == "users":
            if not is_admin(chat_id):
                tg_answer_cb(cq_id, "🔒 Admin only", show_alert=True)
                return
            tg_edit(chat_id, mid, msg_users(), kb_admin())

        elif data == "debug":
            if not is_admin(chat_id):
                tg_answer_cb(cq_id, "🔒 Admin only", show_alert=True)
                return
            tg_typing(chat_id)
            tg_edit(chat_id, mid, msg_processing())
            status, resp = amarseba_balance()
            if status == 200 and resp.get("success"):
                st = state_read()
                src = "telegram_pin" if (st and st.get("api_key")) else (
                    "memory" if _memory_state["api_key"] else "default"
                )
                tg_edit(chat_id, mid, msg_debug(chat_id, resp["data"], src), kb_admin())
            else:
                tg_edit(chat_id, mid, msg_error(status, resp), kb_admin())

    except Exception as e:
        print(f"callback error: {e}")
        print(traceback.format_exc())


# ============================================================
# MAIN HANDLER
# ============================================================
def handle_update(update):
    try:
        if "callback_query" in update:
            cq = update["callback_query"]
            track_user(cq["message"]["chat"]["id"])
            return handle_callback(cq)

        msg = update.get("message") or update.get("edited_message")
        if not msg:
            return
        chat_id = msg["chat"]["id"]
        text = (msg.get("text") or "").strip()
        print(f"In: {chat_id} {text!r}")
        if not text:
            return

        track_user(chat_id)

        if not is_admin(chat_id) and not is_bot_on():
            tg_send(chat_id, msg_bot_off())
            return

        if text in ("/start", "/help"):
            return cmd_start(chat_id) if text == "/start" else cmd_help(chat_id)
        if text == "/id": return cmd_id(chat_id)
        if text == "/balance": return cmd_balance(chat_id)
        if text == "/history": return cmd_history(chat_id)
        if text == "/clearhistory": return cmd_clearhistory(chat_id)
        if text == "/debug": return cmd_debug(chat_id)
        if text == "/delkey": return cmd_delkey(chat_id)
        if text == "/botoff": return cmd_botoff(chat_id)
        if text == "/boton": return cmd_boton(chat_id)
        if text == "/botstatus": return cmd_botstatus(chat_id)
        if text == "/users": return cmd_users(chat_id)
        if text == "/resetusers": return cmd_resetusers(chat_id)
        if text == "/cleanstate": return cmd_cleanstate(chat_id)
        if text.startswith("/setkey"):
            return cmd_setkey(chat_id, text[7:].strip())

        payload = text[5:].strip() if text.startswith("/send") else text
        parts = payload.split(None, 1)
        if len(parts) < 2:
            tg_send(chat_id,
                f"⚠️ <b>Wrong format</b>\n\n{SEP}\n\n"
                f"<b>Correct:</b>\n<code>01712345678 your message</code>\n\n"
                f"📖 /help",
                reply_markup=kb_main())
            return
        return cmd_send_sms(chat_id, parts[0], parts[1].strip())

    except Exception as e:
        print(f"CRASH: {e}")
        print(traceback.format_exc())
        try:
            tg_send(msg["chat"]["id"],
                f"⚠️ <b>Internal Error</b>\n\n<code>{str(e)[:200]}</code>")
        except Exception:
            pass


# ============================================================
# FLASK ROUTES
# ============================================================
@app.route("/", methods=["GET", "POST"])
def root():
    if request.method == "POST":
        update = request.get_json(silent=True) or {}
        try:
            handle_update(update)
        except Exception as e:
            print(f"root err: {e}")
        return jsonify({"ok": True})
    return jsonify({
        "status": "ok",
        "bot": BOT_NAME,
        "developer": "@shakib2016",
        "bot_on": is_bot_on(),
        "user_count": get_user_stats()["count"],
        "history_count": len(get_history()),
    })


@app.route("/webhook", methods=["GET", "POST"])
@app.route("/api/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "POST":
        update = request.get_json(silent=True) or {}
        try:
            handle_update(update)
        except Exception as e:
            print(f"wh err: {e}")
        return jsonify({"ok": True})
    return jsonify({"status": "ok"})


@app.route("/set-webhook", methods=["GET"])
def set_webhook():
    host = request.host_url.rstrip("/")
    url = f"{host}/webhook"
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook",
            params={"url": url, "drop_pending_updates": "true"}, timeout=20,
        )
        return jsonify({"webhook_url": url, "result": r.json()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/webhook-info", methods=["GET"])
def webhook_info():
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getWebhookInfo",
            timeout=20,
        )
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/delete-webhook", methods=["GET"])
def delete_webhook():
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook",
            timeout=20,
        )
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/test-telegram", methods=["GET"])
def test_telegram():
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe",
            timeout=20,
        )
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/test-amarseba", methods=["GET"])
def test_amarseba():
    try:
        r = scraper.get(
            f"{AMARSEBA_BASE_URL}/wallet/balance",
            headers=get_headers(), timeout=30,
        )
        try:
            return jsonify({"http_status": r.status_code, "response": r.json()})
        except Exception:
            return jsonify({"http_status": r.status_code, "raw": r.text[:500]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(port=5000, debug=True)
