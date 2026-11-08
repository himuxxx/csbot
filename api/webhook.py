"""
Amarseba SMS Telegram Bot — Vercel
Bot ON/OFF toggle (admin) + auto Processing→Sent + English UI
"""
import time
import json
import uuid
import traceback
import requests
import cloudscraper
from flask import Flask, request, jsonify

# ==================== CONFIG ====================
TELEGRAM_BOT_TOKEN = "8896805760:AAFYDVaKzleuPINa0AjlBSsrbBR8IytO3S0"
AMARSEBA_API_KEY_DEFAULT = "sk-ams-live-Xqoc4Aley0GyV8XbzXjZCdReeePqOrpYSjNP0Cc5k8pnFLLh"
AMARSEBA_BASE_URL = "https://e-amarseba.com/api/v1"

ADMIN_CHAT_IDS = ["6552783238", "1700797877"]

# Storage: one pinned message holds JSON state
STORE_PREFIX = "🔑AMARSEBA_STATE::"
LEGACY_KEY_PREFIX = "🔑AMARSEBA_KEY::"

DEV_NAME = "SHAKIB"
DEV_LINK = "https://t.me/shakib2016"
BOT_NAME = "SAKIB CUSTOM SMS BOT"
SEP = "━━━━━━━━━━━━━━━━━━━━━━━━"
# ================================================

app = Flask(__name__)

scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "desktop": True}
)

# In-memory fallback (per warm instance)
_memory_state = {"api_key": None, "bot_on": True}


# ============================================================
# TELEGRAM-BASED STORAGE (JSON in pinned message)
# ============================================================
def _storage_chat():
    return ADMIN_CHAT_IDS[0] if ADMIN_CHAT_IDS else None


def state_read():
    """Read {api_key, bot_on} from pinned message."""
    chat = _storage_chat()
    if not chat:
        return None
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getChat",
            params={"chat_id": chat}, timeout=15,
        )
        j = r.json()
        if not j.get("ok"):
            return None
        pinned = (j.get("result") or {}).get("pinned_message") or {}
        text = pinned.get("text", "") or ""
        if text.startswith(STORE_PREFIX):
            try:
                data = json.loads(text[len(STORE_PREFIX):])
            except Exception:
                data = {}
            return {
                "api_key": (data.get("api_key") or None),
                "bot_on": bool(data.get("bot_on", True)),
            }
        if text.startswith(LEGACY_KEY_PREFIX):
            k = text[len(LEGACY_KEY_PREFIX):].strip()
            return {"api_key": (k or None), "bot_on": True}
    except Exception as e:
        print(f"state_read error: {e}")
    return None


def state_write(state):
    """Write {api_key, bot_on} to pinned message."""
    chat = _storage_chat()
    if not chat:
        return False
    try:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/unpinAllChatMessages",
                json={"chat_id": chat}, timeout=10,
            )
        except Exception:
            pass
        payload = {
            "api_key": state.get("api_key") or "",
            "bot_on": bool(state.get("bot_on", True)),
        }
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": chat,
                "text": f"{STORE_PREFIX}{json.dumps(payload)}",
                "disable_notification": True,
            }, timeout=15,
        )
        j = r.json()
        if not j.get("ok"):
            return False
        msg_id = j["result"]["message_id"]
        pr = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/pinChatMessage",
            json={
                "chat_id": chat,
                "message_id": msg_id,
                "disable_notification": True,
            }, timeout=15,
        )
        return pr.json().get("ok", False)
    except Exception as e:
        print(f"state_write error: {e}")
        return False


# ============================================================
# KEY + STATE MANAGEMENT
# ============================================================
def get_api_key():
    st = state_read()
    if st and st.get("api_key"):
        return st["api_key"]
    if _memory_state["api_key"]:
        return _memory_state["api_key"]
    return AMARSEBA_API_KEY_DEFAULT


def is_bot_on():
    st = state_read()
    if st is not None:
        return bool(st.get("bot_on", True))
    return bool(_memory_state.get("bot_on", True))


def set_api_key(new_key):
    st = state_read() or {"api_key": None, "bot_on": True}
    st["api_key"] = new_key
    _memory_state["api_key"] = new_key
    if state_write(st):
        return "blob"
    return "memory"


def clear_api_key():
    _memory_state["api_key"] = None
    st = state_read() or {"api_key": None, "bot_on": True}
    st["api_key"] = ""
    state_write(st)


def set_bot_on(value):
    st = state_read() or {"api_key": None, "bot_on": True}
    st["bot_on"] = bool(value)
    _memory_state["bot_on"] = bool(value)
    if st.get("api_key"):
        _memory_state["api_key"] = st["api_key"]
    return state_write(st)


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


def tg_send_and_get_id(chat_id, text, reply_markup=None, parse_mode="HTML"):
    j = tg_send(chat_id, text, reply_markup, parse_mode)
    if j.get("ok"):
        return j["result"]["message_id"]
    return None


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
# INLINE KEYBOARDS
# ============================================================
def kb_main():
    return {"inline_keyboard": [
        [
            {"text": "💰 Balance", "callback_data": "balance"},
            {"text": "📖 Help", "callback_data": "help"},
        ],
        [{"text": "👨‍💻 Developer", "url": DEV_LINK}],
    ]}


def kb_help():
    return {"inline_keyboard": [
        [
            {"text": "💰 Balance", "callback_data": "balance"},
            {"text": "🏠 Home", "callback_data": "home"},
        ],
        [{"text": "👨‍💻 Developer", "url": DEV_LINK}],
    ]}


def kb_balance():
    return {"inline_keyboard": [
        [
            {"text": "🔄 Refresh", "callback_data": "balance"},
            {"text": "📖 Help", "callback_data": "help"},
        ],
        [
            {"text": "🏠 Home", "callback_data": "home"},
            {"text": "👨‍💻 Developer", "url": DEV_LINK},
        ],
    ]}


def kb_admin():
    return {"inline_keyboard": [
        [
            {"text": "💰 Balance", "callback_data": "balance"},
            {"text": "🔍 Debug", "callback_data": "debug"},
        ],
        [
            {"text": "📖 Help", "callback_data": "help"},
            {"text": "👨‍💻 Developer", "url": DEV_LINK},
        ],
    ]}


def kb_sms():
    return {"inline_keyboard": [
        [
            {"text": "🏠 Home", "callback_data": "home"},
            {"text": "💰 Balance", "callback_data": "balance"},
        ],
        [
            {"text": "📖 Help", "callback_data": "help"},
            {"text": "👨‍💻 Developer", "url": DEV_LINK},
        ],
    ]}


# ============================================================
# MESSAGE BUILDERS
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
            f"  • /blob-test — Storage test\n"
            f"  • /botoff — Turn OFF bot\n"
            f"  • /boton — Turn ON bot\n"
            f"  • /botstatus — Bot state\n\n"
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
    return "⏳", "Processing"


def msg_sms_details(phone, status="processing", cost=None, balance_after=None):
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
    lines.append("")
    lines.append(SEP)
    return "\n".join(lines)


def msg_error(status, data):
    msg = data.get("message", "Unknown error") if isinstance(data, dict) else str(data)
    return (
        f"❌ <b>Error Occurred</b>\n\n"
        f"{SEP}\n\n"
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
    storage = "✅ Telegram pinned" if state_read() else "⚠️ no pin"
    bot_state = "🟢 ON" if is_bot_on() else "🔴 OFF"
    return (
        f"🔍 <b>System Status</b>\n\n"
        f"┏━━━━━━━━━━━━━━━━━━━┓\n"
        f"   💰 <b>{d.get('balance')} {d.get('currency')}</b>\n"
        f"┗━━━━━━━━━━━━━━━━━━━┛\n\n"
        f"📌 Status: <b>{d.get('status', 'active').upper()}</b>\n"
        f"🤖 Bot: <b>{bot_state}</b>\n"
        f"🔑 Key: <code>{mask_key(get_api_key())}</code>\n"
        f"📦 Source: <b>{src}</b>\n"
        f"🗄️ Storage: {storage}\n"
        f"👑 Admin: {'✅ Yes' if is_admin(chat_id) else '❌ No'}\n\n"
        f"{SEP}"
    )


def msg_bot_off():
    return (
        f"🔴 <b>Bot is Currently OFF</b>\n\n"
        f"{SEP}\n\n"
        f"⚠️ The bot has been temporarily disabled by the admin.\n\n"
        f"🕐 Please try again later.\n\n"
        f"{SEP}\n\n"
        f"👨‍💻 <b>Need help?</b>\n"
        f"👉 <a href=\"{DEV_LINK}\">@shakib2016</a>"
    )


def msg_bot_toggled(is_on, persisted):
    icon = "🟢" if is_on else "🔴"
    state = "ON" if is_on else "OFF"
    if persisted:
        note = "🔒 Persists across cold starts"
    else:
        note = "⚠️ Memory only — will reset on cold start"
    desc = (
        "Users can now use the bot normally."
        if is_on
        else "Non-admin users will see \"Bot is OFF\" message."
    )
    return (
        f"{icon} <b>Bot is Now {state}</b>\n\n"
        f"{SEP}\n\n"
        f"{desc}\n\n"
        f"{note}\n\n"
        f"{SEP}"
    )


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


def extract_status(batch_data):
    if not isinstance(batch_data, dict):
        return None
    st = batch_data.get("status")
    if st:
        return str(st).lower()
    counts = batch_data.get("counts") or {}
    if isinstance(counts, dict) and counts:
        def _i(k):
            try:
                return int(counts.get(k, 0))
            except Exception:
                return 0
        sent = _i("sent")
        failed = _i("failed")
        queued = _i("queued")
        sending = _i("sending")
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
# COMMAND HANDLERS
# ============================================================
def cmd_start(chat_id):
    kb = kb_admin() if is_admin(chat_id) else kb_main()
    tg_send(chat_id, msg_welcome(chat_id), reply_markup=kb)


def cmd_help(chat_id):
    tg_send(chat_id, msg_help(chat_id), reply_markup=kb_help())


def cmd_id(chat_id):
    tg_send(
        chat_id,
        f"🆔 <b>Your Chat ID</b>\n\n"
        f"{SEP}\n\n"
        f"<code>{chat_id}</code>\n\n"
        f"{SEP}\n\n"
        f"💡 Copy this and send it to the developer",
        reply_markup=kb_main(),
    )


def cmd_balance(chat_id):
    tg_typing(chat_id)
    proc_id = tg_send_and_get_id(chat_id, msg_processing())
    status, data = amarseba_balance()
    if status == 200 and data.get("success"):
        d = data["data"]
        if proc_id:
            tg_edit(chat_id, proc_id, msg_balance(d), reply_markup=kb_balance())
        else:
            tg_send(chat_id, msg_balance(d), reply_markup=kb_balance())
    else:
        err = msg_error(status, data)
        if proc_id:
            tg_edit(chat_id, proc_id, err, reply_markup=kb_main())
        else:
            tg_send(chat_id, err, reply_markup=kb_main())


def cmd_debug(chat_id):
    if not is_admin(chat_id):
        tg_send(
            chat_id,
            f"🔒 <b>Admin-only command</b>\n\n"
            f"{SEP}\n\n"
            f"📖 How to use: /help\n"
            f"💡 Your info: /id",
            reply_markup=kb_main(),
        )
        return

    tg_typing(chat_id)
    proc_id = tg_send_and_get_id(chat_id, msg_processing())
    status, data = amarseba_balance()
    if status == 200 and data.get("success"):
        d = data["data"]
        st = state_read()
        if st and st.get("api_key"):
            src = "telegram_pin"
        elif _memory_state["api_key"]:
            src = "memory"
        else:
            src = "default"
        text = msg_debug(chat_id, d, src)
        if proc_id:
            tg_edit(chat_id, proc_id, text, reply_markup=kb_admin())
        else:
            tg_send(chat_id, text, reply_markup=kb_admin())
    else:
        err = msg_error(status, data)
        if proc_id:
            tg_edit(chat_id, proc_id, err, reply_markup=kb_admin())
        else:
            tg_send(chat_id, err, reply_markup=kb_admin())


def cmd_setkey(chat_id, new_key):
    if not is_admin(chat_id):
        tg_send(
            chat_id,
            f"🔒 <b>Only admin can set API key</b>\n\n"
            f"{SEP}\n\n"
            f"🆔 Your chat ID:\n<code>{chat_id}</code>\n\n"
            f"💡 Send this to the developer",
            reply_markup=kb_main(),
        )
        return

    if not new_key:
        tg_send(
            chat_id,
            f"📝 <b>Usage</b>\n\n{SEP}\n\n"
            f"<code>/setkey sk-ams-live-...</code>",
        )
        return

    if not new_key.startswith("sk-ams-"):
        tg_send(chat_id, f"❌ API key must start with <code>sk-ams-</code>")
        return

    proc_id = tg_send_and_get_id(chat_id, "⏳ Saving API key...")
    where = set_api_key(new_key)

    if where == "blob":
        text = (
            f"✅ <b>API key saved</b>\n\n{SEP}\n\n"
            f"🔑 <code>{mask_key(new_key)}</code>\n\n"
            f"📌 Stored in pinned message\n"
            f"🔒 Persists across cold starts\n\n"
            f"💡 Test with /balance"
        )
    else:
        text = (
            f"⚠️ <b>Saved in memory only</b>\n\n{SEP}\n\n"
            f"🔑 <code>{mask_key(new_key)}</code>\n\n"
            f"⏱️ Lost after cold start (~15-30 min)"
        )
    if proc_id:
        tg_edit(chat_id, proc_id, text)
    else:
        tg_send(chat_id, text)


def cmd_delkey(chat_id):
    if not is_admin(chat_id):
        tg_send(chat_id, f"🔒 Admin only", reply_markup=kb_main())
        return
    clear_api_key()
    tg_send(
        chat_id,
        f"🗑️ <b>API key deleted</b>\n\n{SEP}\n\n"
        f"Now using default key",
    )


def cmd_blob_test(chat_id):
    if not is_admin(chat_id):
        tg_send(chat_id, f"🔒 Admin only", reply_markup=kb_main())
        return
    chat = _storage_chat()
    if not chat:
        tg_send(chat_id, f"❌ <b>Storage fail</b>\n\nNo admin configured")
        return
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getChat",
            params={"chat_id": chat}, timeout=15,
        )
        j = r.json()
        pinned = (j.get("result") or {}).get("pinned_message") or {}
        ptext = (pinned.get("text", "") or "")[:60]
        st = state_read() or {}
        tg_send(
            chat_id,
            f"✅ <b>Storage Info</b>\n\n{SEP}\n\n"
            f"💬 Chat: <code>{chat}</code>\n"
            f"📌 Pinned: <code>{ptext}</code>\n"
            f"🔑 Has key: {bool(st.get('api_key'))}\n"
            f"🤖 Bot ON: {bool(st.get('bot_on', True))}",
        )
    except Exception as e:
        tg_send(
            chat_id,
            f"❌ <b>Storage fail</b>\n\nReason: <code>{e}</code>",
        )


def cmd_botoff(chat_id):
    if not is_admin(chat_id):
        tg_send(chat_id, f"🔒 Admin only", reply_markup=kb_main())
        return
    persisted = set_bot_on(False)
    tg_send(chat_id, msg_bot_toggled(False, persisted), reply_markup=kb_admin())


def cmd_boton(chat_id):
    if not is_admin(chat_id):
        tg_send(chat_id, f"🔒 Admin only", reply_markup=kb_main())
        return
    persisted = set_bot_on(True)
    tg_send(chat_id, msg_bot_toggled(True, persisted), reply_markup=kb_admin())


def cmd_botstatus(chat_id):
    if not is_admin(chat_id):
        tg_send(chat_id, f"🔒 Admin only", reply_markup=kb_main())
        return
    on = is_bot_on()
    icon = "🟢" if on else "🔴"
    state = "ON" if on else "OFF"
    tg_send(
        chat_id,
        f"{icon} <b>Bot Status: {state}</b>\n\n{SEP}\n\n"
        f"{'Users can use the bot normally.' if on else 'Non-admin users are blocked.'}\n\n"
        f"💡 Toggle: /botoff or /boton",
        reply_markup=kb_admin(),
    )


def cmd_send_sms(chat_id, phone, body):
    if not is_valid_phone(phone):
        tg_send(
            chat_id,
            f"❌ <b>Invalid phone</b>\n\n{SEP}\n\n"
            f"<b>Format:</b>\n<code>01712345678 your message</code>",
            reply_markup=kb_main(),
        )
        return

    if not body:
        tg_send(chat_id, "❌ Message is empty", reply_markup=kb_main())
        return

    tg_typing(chat_id)
    proc_id = tg_send_and_get_id(chat_id, msg_processing())

    status, data = amarseba_send(phone, body)

    if not (status in (200, 201, 202) and data.get("success")):
        text = msg_error(status, data)
        if proc_id:
            tg_edit(chat_id, proc_id, text, reply_markup=kb_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_main())
        return

    d = data.get("data", {}) or {}
    batch_id = d.get("batch_id", "")
    cost = d.get("total_cost")
    balance_after = d.get("balance_after")

    # Step 1: Processing message
    proc_text = msg_sms_details(
        phone, status="processing", cost=cost, balance_after=balance_after,
    )
    if proc_id:
        tg_edit(chat_id, proc_id, proc_text, reply_markup=kb_sms())
    else:
        proc_id = tg_send_and_get_id(chat_id, proc_text, reply_markup=kb_sms())

    # Step 2: Wait 1.5s → check batch → final status
    final_status = "sent"
    if batch_id:
        try:
            time.sleep(1.5)
            st_code, st_resp = amarseba_batch(batch_id)
            if st_code == 200 and st_resp.get("success"):
                bd = st_resp.get("data", {}) or {}
                extracted = extract_status(bd)
                if str(extracted).lower() == "failed":
                    final_status = "failed"
                elif str(extracted).lower() in ("sent", "delivered"):
                    final_status = "sent"
        except Exception as e:
            print(f"batch status check error: {e}")

    final_text = msg_sms_details(
        phone, status=final_status, cost=cost, balance_after=balance_after,
    )
    if proc_id:
        tg_edit(chat_id, proc_id, final_text, reply_markup=kb_sms())
    else:
        tg_send(chat_id, final_text, reply_markup=kb_sms())


# ============================================================
# CALLBACK HANDLER
# ============================================================
def handle_callback(cq):
    try:
        cq_id = cq["id"]
        chat_id = cq["message"]["chat"]["id"]
        message_id = cq["message"]["message_id"]
        data = cq.get("data", "")

        # Bot OFF gate for non-admin
        if not is_admin(chat_id) and not is_bot_on():
            tg_answer_cb(cq_id, "🔴 Bot is OFF", show_alert=True)
            return

        tg_answer_cb(cq_id)

        if data == "balance":
            tg_typing(chat_id)
            tg_edit(chat_id, message_id, msg_processing())
            status, resp = amarseba_balance()
            if status == 200 and resp.get("success"):
                tg_edit(
                    chat_id, message_id,
                    msg_balance(resp["data"]),
                    reply_markup=kb_balance(),
                )
            else:
                tg_edit(
                    chat_id, message_id,
                    msg_error(status, resp),
                    reply_markup=kb_main(),
                )

        elif data == "help":
            tg_edit(chat_id, message_id, msg_help(chat_id), reply_markup=kb_help())

        elif data == "home":
            kb = kb_admin() if is_admin(chat_id) else kb_main()
            tg_edit(chat_id, message_id, msg_welcome(chat_id), reply_markup=kb)

        elif data == "debug":
            if not is_admin(chat_id):
                tg_answer_cb(cq_id, "🔒 Admin only", show_alert=True)
                return
            tg_typing(chat_id)
            tg_edit(chat_id, message_id, msg_processing())
            status, resp = amarseba_balance()
            if status == 200 and resp.get("success"):
                st = state_read()
                if st and st.get("api_key"):
                    src = "telegram_pin"
                elif _memory_state["api_key"]:
                    src = "memory"
                else:
                    src = "default"
                tg_edit(
                    chat_id, message_id,
                    msg_debug(chat_id, resp["data"], src),
                    reply_markup=kb_admin(),
                )
            else:
                tg_edit(
                    chat_id, message_id,
                    msg_error(status, resp),
                    reply_markup=kb_admin(),
                )

    except Exception as e:
        print(f"handle_callback error: {e}")
        print(traceback.format_exc())


# ============================================================
# MAIN UPDATE HANDLER
# ============================================================
def handle_update(update):
    try:
        if "callback_query" in update:
            return handle_callback(update["callback_query"])

        message = update.get("message") or update.get("edited_message")
        if not message:
            return

        chat_id = message["chat"]["id"]
        text = (message.get("text") or "").strip()
        print(f"Incoming: chat_id={chat_id} text={text!r}")

        if not text:
            return

        # Bot OFF gate (admin bypasses)
        if not is_admin(chat_id) and not is_bot_on():
            tg_send(chat_id, msg_bot_off())
            return

        if text in ("/start", "/help"):
            return cmd_start(chat_id) if text == "/start" else cmd_help(chat_id)
        if text == "/id":
            return cmd_id(chat_id)
        if text == "/balance":
            return cmd_balance(chat_id)
        if text == "/debug":
            return cmd_debug(chat_id)
        if text == "/delkey":
            return cmd_delkey(chat_id)
        if text == "/blob-test":
            return cmd_blob_test(chat_id)
        if text == "/botoff":
            return cmd_botoff(chat_id)
        if text == "/boton":
            return cmd_boton(chat_id)
        if text == "/botstatus":
            return cmd_botstatus(chat_id)
        if text.startswith("/setkey"):
            arg = text[7:].strip()
            return cmd_setkey(chat_id, arg)

        if text.startswith("/send"):
            payload = text[5:].strip()
        else:
            payload = text

        parts = payload.split(None, 1)
        if len(parts) < 2:
            tg_send(
                chat_id,
                f"⚠️ <b>Wrong format</b>\n\n{SEP}\n\n"
                f"<b>Correct:</b>\n<code>01712345678 your message</code>\n\n"
                f"💡 <b>Example:</b>\n<code>01712345678 Hello</code>\n\n"
                f"{SEP}\n\n📖 Details: /help",
                reply_markup=kb_main(),
            )
            return

        phone, body = parts[0], parts[1].strip()
        return cmd_send_sms(chat_id, phone, body)

    except Exception as e:
        print(f"handle_update CRASH: {e}")
        print(traceback.format_exc())
        try:
            tg_send(
                message["chat"]["id"],
                f"⚠️ <b>Internal Error</b>\n\n"
                f"<code>{str(e)[:200]}</code>\n\n"
                f"Developer: @shakib2016",
            )
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
            print(f"root POST error: {e}")
        return jsonify({"ok": True})
    return jsonify({
        "status": "ok",
        "bot": BOT_NAME,
        "developer": "@shakib2016",
        "admins": ADMIN_CHAT_IDS,
        "storage": "telegram_pinned_message",
        "bot_on": is_bot_on(),
    })


@app.route("/webhook", methods=["GET", "POST"])
@app.route("/api/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "POST":
        update = request.get_json(silent=True) or {}
        try:
            handle_update(update)
        except Exception as e:
            print(f"webhook POST error: {e}")
        return jsonify({"ok": True})
    return jsonify({"status": "ok", "endpoint": "webhook"})


@app.route("/blob-info", methods=["GET"])
def blob_info():
    st = state_read() or {}
    return jsonify({
        "storage_type": "telegram_pinned_message",
        "chat_id": _storage_chat(),
        "has_key": bool(st.get("api_key")),
        "bot_on": bool(st.get("bot_on", True)),
    })


@app.route("/set-webhook", methods=["GET"])
def set_webhook():
    host = request.host_url.rstrip("/")
    url = f"{host}/webhook"
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook",
            params={"url": url, "drop_pending_updates": "true"},
            timeout=20,
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
        src = "telegram_pin" if (state_read() or {}).get("api_key") else (
            "memory" if _memory_state["api_key"] else "default"
        )
        try:
            return jsonify({
                "http_status": r.status_code,
                "key_source": src,
                "bot_on": is_bot_on(),
                "response": r.json(),
            })
        except Exception:
            return jsonify({"http_status": r.status_code, "raw": r.text[:500]})
    except Exception as e:
        return jsonify({
            "ok": False,
            "error_class": e.__class__.__name__,
            "error": str(e),
        }), 500


if __name__ == "__main__":
    app.run(port=5000, debug=True)
