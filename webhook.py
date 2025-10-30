from flask import Flask, request
import requests, os
from dotenv import load_dotenv
from openpyxl import load_workbook
from langdetect import detect, DetectorFactory
import google.generativeai as genai
from waitress import serve

# =========================
# INITIAL SETUP
# =========================
app = Flask(__name__)
load_dotenv()
VERIFY_TOKEN = "123abc"

DetectorFactory.seed = 0

# =========================
# LOAD EXCEL CONFIG
# =========================
PAGE_CONFIG = {}
AI_COMMANDS = {}

def load_page_config():
    """Load page info: page_id, token, gemini key, store link"""
    wb = load_workbook("pages_config.xlsx", read_only=True)
    ws = wb.active
    for row in ws.iter_rows(min_row=2, values_only=True):
        page_name, page_id, token, gemini_key, store_link = row
        if page_id:
            PAGE_CONFIG[str(page_id)] = {
                "token": token,
                "gemini": gemini_key,
                "store": store_link
            }

def load_ai_commands():
    """Load AI command triggers from ai_commands.xlsx"""
    wb = load_workbook("ai_commands.xlsx", read_only=True)
    ws = wb.active
    for row in ws.iter_rows(min_row=2, values_only=True):
        mode_key, trigger_keywords, action_desc, ai_prompt = row
        if trigger_keywords:
            keywords = [k.strip().lower() for k in trigger_keywords.split(",")]
            AI_COMMANDS[mode_key] = {
                "keywords": keywords,
                "prompt": ai_prompt
            }

load_page_config()
load_ai_commands()

# =========================
# LANGUAGE DETECTION FIX
# =========================
def detect_language_safe(text):
    try:
        # nếu quá ngắn, mặc định English
        if len(text.strip()) < 5:
            return "en"
        lang = detect(text)
        # tránh lỗi nhận Finnish khi người dùng nói tiếng Anh
        if lang not in ["en", "vi", "es", "fr", "de", "pt", "it"]:
            return "en"
        if text.lower().startswith("i miss"):
            return "en"
        return lang
    except:
        return "en"

# =========================
# SEND MESSAGE FUNCTION
# =========================
def send_message(recipient_id, text, page_id):
    try:
        token = PAGE_CONFIG[str(page_id)]["token"]
        url = f"https://graph.facebook.com/v17.0/me/messages?access_token={token}"
        payload = {"recipient": {"id": recipient_id}, "message": {"text": text}}
        requests.post(url, json=payload)
    except Exception as e:
        print("❌ Send message error:", e)

# =========================
# DETECT MODE
# =========================
def detect_mode(message):
    msg = message.lower()
    for mode, data in AI_COMMANDS.items():
        for kw in data["keywords"]:
            if kw in msg:
                return mode
    return "chat_mode"

# =========================
# GENERATE AI RESPONSE
# =========================
def generate_reply(message, api_key, role="chat_mode"):
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")

        lang = detect_language_safe(message)

        if role == "buy_product":
            system_prompt = (
                "You are a Heaven Store sales assistant. "
                "Speak warmly and naturally. If the user asks about products, "
                "send the Heaven Store link politely. "
                "Always reply in the same language as user."
            )
        else:
            system_prompt = (
                "You are a compassionate Heaven psychologist assistant. "
                "Speak softly, kindly, and comfort those who miss loved ones. "
                "Use empathy and emotional intelligence. "
                "Always reply in the same language as user."
            )

        prompt = f"{system_prompt}\nUser message: {message}\nLanguage: {lang}"
        response = model.generate_content(prompt)
        return response.text.strip() if response.text else "..."
    except Exception as e:
        print("⚠️ Gemini error:", e)
        return "Sorry, I'm having trouble replying right now."

# =========================
# VERIFY WEBHOOK
# =========================
@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("✅ Webhook verified successfully!")
        return challenge, 200
    else:
        print("❌ Verification failed.")
        return "Verification token mismatch", 403

# =========================
# HANDLE MESSAGES
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if data.get("object") == "page":
        for entry in data.get("entry", []):
            page_id = str(entry.get("id"))
            for event in entry.get("messaging", []):
                if "message" in event and "text" in event["message"]:
                    sender_id = event["sender"]["id"]
                    message = event["message"]["text"].strip()

                    mode = detect_mode(message)
                    config = PAGE_CONFIG.get(page_id, {})
                    gemini_key = config.get("gemini")

                    # --- Nếu là yêu cầu mua hàng ---
                    if mode == "buy_product":
                        store_link = config.get("store", "")
                        if store_link:
                            reply = (
                                f"🛒 You can explore our Heaven Store here:\n"
                                f"{store_link}\n\n"
                                "Would you like me to show some memorial gifts?"
                            )
                        else:
                            reply = "Our store link isn’t configured yet."
                    else:
                        # --- Tâm lý Heaven mode ---
                        reply = generate_reply(message, gemini_key, role="chat_mode")

                    send_message(sender_id, reply, page_id)

    return "OK", 200

# =========================
# HOME PAGE
# =========================
@app.route("/", methods=["GET"])
def home():
    return "✅ HeavenBot is active and ready.", 200

# =========================
# START SERVER
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🚀 HeavenBot running on port {port}")
    serve(app, host="0.0.0.0", port=port)
