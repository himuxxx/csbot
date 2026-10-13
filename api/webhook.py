"""
Amarseba SMS Telegram Bot — Vercel Webhook (FIXED)
"""
import uuid
import requests
from flask import Flask, request, jsonify

# ==================== CONFIG ====================
TELEGRAM_BOT_TOKEN = "8426186448:AAFUcpPA0Kn-q4pD-h9OAanUy64KtQbrDxk"
AMARSEBA_API_KEY   = "sk-ams-live-Xqoc4Aley0GyV8XbzXjZCdReeePqOrpYSjNP0Cc5k8pnFLLh"
AMARSEBA_BASE_URL  = "https://e-amarseba.com/api/v1"
# ================================================

app = Flask(__name__)

HEADERS = {
    "Authorization": f"Bearer {AMARSEBA_API_KEY}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}


# ---------------- Telegram helpers ----------------
def tg_send(chat_id, text, parse_mode="HTML"):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            timeout=20,
        )
    except Exception as e:
        print(f"tg_send error: {e}")


def tg_typing(chat_id):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendChatAction",
            json={"chat_id": chat_id, "action": "typing"},
            timeout=10,
        )
    except Exception:
        pass


# ---------------- Amarseba helpers ----------------
def amarseba_send(phone, body):
    h = HEADERS.copy()
    h["Idempotency-Key"] = str(uuid.uuid4())
    r = requests.post(
        f"{AMARSEBA_BASE_URL}/bulk-sms/send",
        headers=h, json={"to": phone, "body": body}, timeout=60,
    )
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"success": False, "message": r.text}


def amarseba_balance():
    r = requests.get(
        f"{AMARSEBA_BASE_URL}/wallet/balance",
        headers=HEADERS, timeout=20,
    )
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"success": False, "message": r.text}


def is_valid_phone(p):
    c = p.replace("+", "").replace("-", "").replace(" ", "")
    return c.isdigit() and 10 <= len(c) <= 14


# ---------------- Update handler ----------------
def handle_update(update):
    message = update.get("message") or update.get("edited_message")
    if not message:
        return

    chat_id = message["chat"]["id"]
    text = (message.get("text") or "").strip()
    if not text:
        return

    # /start, /help
    if text in ("/start", "/help"):
        welcome = (
            "🤖 <b>Amarseba SMS Bot</b>\n\n"
            "SMS পাঠাতে এই ফরম্যাটে মেসেজ দিন:\n"
            "<code>01712345678 আপনার মেসেজ</code>\n\n"
            "<b>কমান্ড:</b>\n"
            "• /send 01712345678 মেসেজ\n"
            "• /balance — ব্যালেন্স\n"
            "• /id — chat ID"
        )
        tg_send(chat_id, welcome)
        return

    # /id
    if text == "/id":
        tg_send(chat_id, f"🆔 আপনার chat ID: <code>{chat_id}</code>")
        return

    # /balance
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
            tg_send(chat_id, f"❌ {data.get('message', 'Error')}")
        return

    # Send SMS
    payload_text = text
    if text.startswith("/send"):
        payload_text = text[5:].strip()

    parts = payload_text.split(None, 1)
    if len(parts) < 2:
        tg_send(chat_id,
            "❌ ফরম্যাট ভুল।\n\n"
            "এভাবে পাঠান:\n"
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
        msg = (
            "✅ <b>SMS পাঠানো হয়েছে!</b>\n\n"
            f"📊 স্ট্যাটাস: <b>{d.get('status', '-')}</b>\n"
            f"👥 প্রাপক: {d.get('recipient_count', '-')}\n"
            f"🧩 পার্ট: {d.get('total_parts', '-')}\n"
            f"💵 খরচ: {d.get('total_cost', '-')}\n"
            f"💰 ব্যালেন্স: {d.get('balance_after', '-')}\n"
            f"🆔 <code>{d.get('batch_id', '-')}</code>"
        )
        tg_send(chat_id, msg)
    else:
        tg_send(chat_id,
            f"❌ <b>HTTP {status}</b>\n"
            f"{data.get('message', 'Error')}"
        )


# ==================== Routes ====================
@app.route("/", methods=["GET", "POST"])
def root():
    if request.method == "POST":
        update = request.get_json(silent=True) or {}
        try:
            handle_update(update)
        except Exception as e:
            print(f"handle_update error: {e}")
        return jsonify({"ok": True})
    return jsonify({"status": "ok", "bot": "Amarseba SMS Bot"})


@app.route("/webhook", methods=["GET", "POST"])
@app.route("/api/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "POST":
        update = request.get_json(silent=True) or {}
        try:
            handle_update(update)
        except Exception as e:
            print(f"handle_update error: {e}")
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


# লোকাল টেস্টের জন্য
if __name__ == "__main__":
    app.run(port=5000, debug=True)
