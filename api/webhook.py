"""
Amarseba SMS Telegram Bot — Vercel
Hardcoded admins + optional jsonblob persistence (no env needed)
"""
import uuid
import traceback
import requests
import cloudscraper
from flask import Flask, request, jsonify

# ==================== CONFIG ====================
TELEGRAM_BOT_TOKEN = "8896805760:AAFYDVaKzleuPINa0AjlBSsrbBR8IytO3S0"
AMARSEBA_API_KEY_DEFAULT = "sk-ams-live-Xqoc4Aley0GyV8XbzXjZCdReeePqOrpYSjNP0Cc5k8pnFLLh"
AMARSEBA_BASE_URL = "https://e-amarseba.com/api/v1"

# ✅ Admin chat_id গুলোর তালিকা (একাধিক হলে comma দিয়ে, কিন্তু list আকারে)
ADMIN_CHAT_IDS = ["6552783238", "1700797877"]

# jsonblob.com থেকে পাওয়া ID এখানে বসান (না থাকলে খালি রাখুন)
BLOB_ID = ""   # ex: "1234567890123456789"
# ================================================

app = Flask(__name__)

scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "desktop": True}
)

_memory_key = {"value": None}


# ---------------- jsonblob storage ----------------
def _blob_url():
    return f"https://jsonblob.com/api/jsonBlob/{BLOB_ID}"


def blob_read():
    if not BLOB_ID:
        return None
    try:
        r = requests.get(_blob_url(), timeout=10)
        if r.status_code == 200:
            return (r.json() or {}).get("api_key") or None
    except Exception as e:
        print(f"blob_read error: {e}")
    return None


def blob_write(api_key):
    if not BLOB_ID:
        return False
    try:
        r = requests.put(
            _blob_url(),
            json={"api_key": api_key},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        return r.status_code in (200, 204)
    except Exception as e:
        print(f"blob_write error: {e}")
        return False


# ---------------- Key management ----------------
def get_api_key():
    k = blob_read()
    if k:
        return k
    if _memory_key["value"]:
        return _memory_key["value"]
    return AMARSEBA_API_KEY_DEFAULT


def set_api_key(new_key):
    if blob_write(new_key):
        _memory_key["value"] = new_key
        return "blob"
    _memory_key["value"] = new_key
    return "memory"


def clear_api_key():
    _memory_key["value"] = None
    if BLOB_ID:
        blob_write("")


def is_admin(chat_id):
    """একাধিক admin সাপোর্ট করে।"""
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


# ---------------- Telegram helpers ----------------
def tg_send(chat_id, text, parse_mode="HTML"):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            timeout=20,
        )
        print(f"tg_send status={r.status_code}")
        return r
    except Exception as e:
        print(f"tg_send error: {e}")
        return None


def tg_typing(chat_id):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendChatAction",
            json={"chat_id": chat_id, "action": "typing"},
            timeout=10,
        )
    except Exception as e:
        print(f"tg_typing error: {e}")


# ---------------- Amarseba helpers ----------------
def amarseba_send(phone, body):
    h = get_headers()
    h["Idempotency-Key"] = str(uuid.uuid4())
    try:
        r = scraper.post(
            f"{AMARSEBA_BASE_URL}/bulk-sms/send",
            headers=h, json={"to": phone, "body": body}, timeout=50,
        )
        print(f"amarseba_send status={r.status_code}")
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
        print(f"amarseba_balance status={r.status_code}")
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, {"success": False, "message": r.text[:300]}
    except Exception as e:
        return 0, {"success": False, "message": str(e)}


def is_valid_phone(p):
    c = p.replace("+", "").replace("-", "").replace(" ", "")
    return c.isdigit() and 10 <= len(c) <= 14


# ---------------- Update handler ----------------
def handle_update(update):
    try:
        message = update.get("message") or update.get("edited_message")
        if not message:
            return

        chat_id = message["chat"]["id"]
        text = (message.get("text") or "").strip()
        print(f"Incoming: chat_id={chat_id} text={text!r}")

        if not text:
            return

        # ---------- /start, /help ----------
        if text in ("/start", "/help"):
            base = (
                "🤖 <b>SAKIB CUSTOM SMS BOT</b>\n\n"
                "SMS পাঠাতে:\n"
                "<code>01712345678 আপনার মেসেজ</code>\n\n"
                "<b>কমান্ড:</b>\n"
                "• /balance — ব্যালেন্স\n"
                "• /id — chat ID\n"
                "• /debug — সিস্টেম টেস্ট\n"
            )
            if is_admin(chat_id):
                base += (
                    "\n<b>👑 Admin কমান্ড:</b>\n"
                    "• /setkey &lt;api_key&gt; — API key সেট\n"
                    "• /delkey — key মুছুন\n"
                    "• /setup-blob — persistent storage তৈরি\n"
                )
            tg_send(chat_id, base)
            return

        # ---------- /id ----------
        if text == "/id":
            tg_send(chat_id, f"🆔 chat ID: <code>{chat_id}</code>")
            return

        # ---------- /setkey (ADMIN ONLY) ----------
        if text.startswith("/setkey"):
            if not is_admin(chat_id):
                tg_send(chat_id,
                    "⛔ শুধুমাত্র admin API key সেট করতে পারবে।\n\n"
                    f"আপনার chat_id: <code>{chat_id}</code>"
                )
                return

            parts = text.split(None, 1)
            if len(parts) < 2:
                tg_send(chat_id, "ব্যবহার: <code>/setkey sk-ams-live-...</code>")
                return

            new_key = parts[1].strip()
            if not new_key.startswith("sk-ams-"):
                tg_send(chat_id, "❌ API key অবশ্যই <code>sk-ams-</code> দিয়ে শুরু হবে।")
                return

            where = set_api_key(new_key)
            if where == "blob":
                tg_send(chat_id,
                    "✅ <b>API key সেভ হয়েছে (persistent)</b>\n\n"
                    f"<code>{mask_key(new_key)}</code>"
                )
            else:
                tg_send(chat_id,
                    "⚠️ <b>API key শুধু memory-তে সেভ হয়েছে</b>\n\n"
                    f"<code>{mask_key(new_key)}</code>\n\n"
                    "⏱️ Vercel cold start হলে (~১৫-৩০ মিনিট) এটা মুছে যাবে।\n\n"
                    "💡 স্থায়ীভাবে সেভ করতে:\n"
                    "1. <code>/setup-blob</code> কমান্ড দিন\n"
                    "2. পাওয়া BLOB_ID কোডে <code>BLOB_ID</code> লাইনে বসান\n"
                    "3. Redeploy করুন"
                )
            return

        # ---------- /delkey (ADMIN ONLY) ----------
        if text == "/delkey":
            if not is_admin(chat_id):
                tg_send(chat_id, "⛔ শুধুমাত্র admin।")
                return
            clear_api_key()
            tg_send(chat_id, "🗑️ API key মুছে ফেলা হয়েছে। এখন default ব্যবহার হবে।")
            return

        # ---------- /setup-blob (ADMIN ONLY) ----------
        if text == "/setup-blob":
            if not is_admin(chat_id):
                tg_send(chat_id, "⛔ শুধুমাত্র admin।")
                return
            try:
                r = requests.post(
                    "https://jsonblob.com/api/jsonBlob",
                    json={"api_key": ""},
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    timeout=15,
                )
                loc = r.headers.get("Location", "")
                blob_id = loc.rstrip("/").split("/")[-1] if loc else ""
                if not blob_id:
                    tg_send(chat_id,
                        f"❌ Blob তৈরি হয়নি\nHTTP: {r.status_code}\n"
                        f"<code>{r.text[:200]}</code>"
                    )
                    return
                tg_send(chat_id,
                    "✅ <b>BLOB তৈরি হয়েছে</b>\n\n"
                    f"BLOB_ID: <code>{blob_id}</code>\n\n"
                    "<b>এখন কী করবেন:</b>\n"
                    f"1. <code>api/webhook.py</code>-এ <code>BLOB_ID = \"{blob_id}\"</code> বসান\n"
                    "2. <code>git push</code> → Vercel redeploy\n"
                    "3. তারপর /setkey দিন — স্থায়ীভাবে সেভ হবে"
                )
            except Exception as e:
                tg_send(chat_id, f"⚠️ Exception: <code>{e}</code>")
            return

        # ---------- /debug ----------
        if text == "/debug":
            tg_typing(chat_id)
            try:
                status, data = amarseba_balance()
                if status == 200 and data.get("success"):
                    d = data["data"]
                    src = "blob" if blob_read() else ("memory" if _memory_key["value"] else "default")
                    tg_send(chat_id,
                        "✅ <b>BOT OK</b>\n\n"
                        f"💰 ব্যালেন্স: {d.get('balance')} {d.get('currency')}\n"
                        f"📌 স্ট্যাটাস: {d.get('status')}\n"
                        f"🔑 Key: <code>{mask_key(get_api_key())}</code>\n"
                        f"📦 Source: {src}\n"
                        f"👑 Admin: {'হ্যাঁ' if is_admin(chat_id) else 'না'}"
                    )
                else:
                    tg_send(chat_id,
                        f"❌ <b>Amarseba fail</b>\nHTTP: {status}\n"
                        f"<code>{str(data)[:300]}</code>"
                    )
            except Exception as e:
                tg_send(chat_id, f"⚠️ Exception: <code>{e}</code>")
            return

        # ---------- /balance ----------
        if text == "/balance":
            tg_typing(chat_id)
            try:
                status, data = amarseba_balance()
            except Exception as e:
                tg_send(chat_id, f"⚠️ Network error: <code>{e}</code>")
                return
            if status == 200 and data.get("success"):
                d = data["data"]
                tg_send(chat_id,
                    f"💰 <b>ব্যালেন্স:</b> {d.get('balance')} {d.get('currency')}\n"
                    f"📌 স্ট্যাটাস: {d.get('status')}"
                )
            else:
                tg_send(chat_id,
                    f"❌ <b>HTTP {status}</b>\n<code>{str(data)[:300]}</code>"
                )
            return

        # ---------- Send SMS ----------
        payload_text = text
        if text.startswith("/send"):
            payload_text = text[5:].strip()

        parts = payload_text.split(None, 1)
        if len(parts) < 2:
            tg_send(chat_id,
                "❌ ফরম্যাট ভুল।\n\nএভাবে পাঠান:\n"
                "<code>01712345678 আপনার মেসেজ</code>"
            )
            return

        phone, body = parts[0], parts[1].strip()
        if not is_valid_phone(phone):
            tg_send(chat_id, "❌ সঠিক নম্বর দিন (যেমন: 01712345678)")
            return
        if not body:
            tg_send(chat_id, "❌ মেসেজ খালি")
            return

        tg_typing(chat_id)
        try:
            status, data = amarseba_send(phone, body)
        except Exception as e:
            tg_send(chat_id, f"⚠️ Network error:\n<code>{e}</code>")
            return

        if status in (200, 201, 202) and data.get("success"):
            d = data.get("data", {})
            tg_send(chat_id,
                "✅ <b>SMS পাঠানো হয়েছে!</b>\n\n"
                f"📊 স্ট্যাটাস: <b>{d.get('status', '-')}</b>\n"
                f"👥 প্রাপক: {d.get('recipient_count', '-')}\n"
                f"🧩 পার্ট: {d.get('total_parts', '-')}\n"
                f"💵 খরচ: {d.get('total_cost', '-')}\n"
                f"💰 ব্যালেন্স: {d.get('balance_after', '-')}\n"
                f"🆔 <code>{d.get('batch_id', '-')}</code>"
            )
        else:
            tg_send(chat_id,
                f"❌ <b>HTTP {status}</b>\n<code>{str(data)[:300]}</code>"
            )

    except Exception as e:
        print(f"handle_update CRASH: {e}")
        print(traceback.format_exc())
        try:
            tg_send(message["chat"]["id"],
                    f"⚠️ Internal error:\n<code>{str(e)[:200]}</code>")
        except Exception:
            pass


# ==================== Routes ====================
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
        "bot": "SAKIB CUSTOM SMS BOT",
        "admins": ADMIN_CHAT_IDS,
        "admin_configured": len(ADMIN_CHAT_IDS) > 0,
        "blob_configured": bool(BLOB_ID),
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


@app.route("/set-webhook", methods=["GET"])
def set_webhook():
    host = request.host_url.rstrip("/")
    webhook_url = f"{host}/webhook"
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook",
            params={"url": webhook_url, "drop_pending_updates": "true"},
            timeout=20,
        )
        return jsonify({"webhook_url": webhook_url, "result": r.json()})
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
        src = "blob" if blob_read() else ("memory" if _memory_key["value"] else "default")
        try:
            return jsonify({
                "http_status": r.status_code,
                "key_source": src,
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
