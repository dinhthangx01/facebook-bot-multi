from flask import Flask, request
import requests, os
from dotenv import load_dotenv
from openpyxl import load_workbook
from langdetect import detect, DetectorFactory
import google.generativeai as genai
from waitress import serve

app = Flask(__name__)
load_dotenv()
VERIFY_TOKEN = "123abc"
DetectorFactory.seed = 0

PAGE_CONFIG, AI_COMMANDS = {}, {}

# ======================
# LOAD CONFIG FROM EXCEL
# ======================
def load_page_config():
    wb = load_workbook("pages_config.xlsx", read_only=True)
    ws = wb.active
    for row in ws.iter_rows(min_row=2, values_only=True):
        page_name, page_id, token, gemini_key, store_link = row
        if page_id:
            PAGE_CONFIG[str(page_id)] = {
                "token": token,
                "gemini": gemini_key,
                "store": store_link or ""
            }

def load_ai_commands():
    wb = load_workbook("ai_commands.xlsx", read_only=True)
    ws = wb.active
    for row in ws.iter_rows(min_row=2, values_only=True):
        mode_key, trigger_keywords, desc, prompt = row
        if trigger_keywords:
            AI_COMMANDS[mode_key] = {
                "keywords": [k.strip().lower() for k in str(trigger_keywords).split(",")],
                "prompt": prompt or ""
            }

load_page_config()
load_ai_commands()

# ======================
# LANGUAGE DETECTION
# ======================
def detect_language_safe(text):
    try:
        if len(text.strip()) < 5:
            return "en"
        lang = detect(text)
        if text.lower().startswith("i miss"):
            return "en"
        if lang not in ["en", "vi", "es", "fr", "de", "pt", "it"]:
            return "en"
        return lang
    except:
        return "en"

# ======================
# SEND MESSAGE
# ======================
def send_message(user_id, text, page_id):
    token = PAGE_CONFIG[str(page_id)]["token"]
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={token}"
    payload = {"recipient": {"id": user_id}, "message": {"text": text}}
    requests.post(url, json=payload)

# ======================
# DETECT MODE
# ======================
def detect_mode(message):
    msg = message.lower()
    for mode, data in AI_COMMANDS.items():
        for keyword in data["keywords"]:
            if keyword in msg:
                return mode
    return "chat_mode"

# ======================
# GENERATE GEMINI RESPONSE
# ======================
def generate_reply(message, api_key, mode="chat_mode"):
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        lang = detect_language_safe(message)

        if mode == "buy_product":
            system_prompt = (
                f"You are a Heaven Store sales assistant. "
                f"User message: '{message}'. "
                f"Reply briefly, warmly, and naturally in {lang}. "
                f"Your message must be under 200 words. "
                f"Do NOT add any external links — only help the user politely."
            )
        else:
            system_prompt = (
                f"You are a compassionate Heaven psychologist. "
                f"User message: '{message}'. "
                f"Reply in {lang}, under 200 words, with empathy and comfort. "
                f"Speak softly and emotionally."
            )

        response = model.generate_content(system_prompt)
        return response.text.strip() if response.text else "..."
    except Exception as e:
        print("⚠️ Gemini error:", e)
        return "Sorry, I’m having trouble replying right now."

# ======================
# VERIFY WEBHOOK
# ======================
@app.route("/webhook", methods=["GET"])
def verify():
    if request.args.get("hub.verify_token") == VERIFY_TOKEN:
        print("✅ Webhook verified successfully!")
        return request.args.get("hub.challenge"), 200
    return "Verification token mismatch", 403

# ======================
# HANDLE MESSAGES
# ======================
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if data.get("object") == "page":
        for entry in data.get("entry", []):
            page_id = str(entry.get("id"))
            for event in entry.get("messaging", []):
                if "message" in event and "text" in event["message"]:
                    sender_id = event["sender"]["id"]
                    user_msg = event["message"]["text"].strip()

                    mode = detect_mode(user_msg)
                    config = PAGE_CONFIG.get(page_id, {})
                    gemini_key = config.get("gemini")

                    # Nếu là chế độ mua hàng
                    if mode == "buy_product":
                        store_link = config.get("store", "")
                        if store_link:
                            ai_reply = generate_reply(user_msg, gemini_key, "buy_product")
                            final_reply = f"{ai_reply}\n\n🛍️ Visit our Heaven Store:\n{store_link}"
                        else:
                            # Nếu không có link, chuyển sang chế độ chat
                            final_reply = generate_reply(user_msg, gemini_key, "chat_mode")
                    else:
                        final_reply = generate_reply(user_msg, gemini_key, "chat_mode")

                    send_message(sender_id, final_reply, page_id)
    return "OK", 200

# ======================
# HOME
# ======================
@app.route("/", methods=["GET"])
def home():
    return "✅ HeavenBot multi-page (auto mode switch, <200 words).", 200

# ======================
# START SERVER
# ======================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🚀 HeavenBot running on port {port}")
    serve(app, host="0.0.0.0", port=port)
