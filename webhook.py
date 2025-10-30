from flask import Flask, request
import requests, os
from dotenv import load_dotenv
from openpyxl import load_workbook
from langdetect import detect
import google.generativeai as genai
from waitress import serve

load_dotenv()
app = Flask(__name__)

VERIFY_TOKEN = "123abc"
PAGE_CONFIG = {}
AI_COMMANDS = {}

# ==== LOAD CONFIG ====
def load_page_config():
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
    wb = load_workbook("ai_commands.xlsx", read_only=True)
    ws = wb.active
    for row in ws.iter_rows(min_row=2, values_only=True):
        mode_key, trigger, desc, prompt = row
        if mode_key:
            AI_COMMANDS[mode_key] = {
                "trigger": [k.strip().lower() for k in str(trigger).split(",")],
                "desc": desc,
                "prompt": prompt
            }

load_page_config()
load_ai_commands()

# ==== SEND MESSAGE ====
def send_message(recipient_id, text, page_id):
    token = PAGE_CONFIG[str(page_id)]["token"]
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={token}"
    payload = {"recipient": {"id": recipient_id}, "message": {"text": text}}
    requests.post(url, json=payload)

# ==== DETECT MODE ====
def detect_mode(message):
    text = message.lower()
    for key, cmd in AI_COMMANDS.items():
        if any(k in text for k in cmd["trigger"]):
            return key
    return "chat_mode"

# ==== GEMINI RESPONSE ====
def generate_reply(message, api_key, prompt=""):
    try:
        genai.configure(api_key=api_key)
        lang = detect(message)
        model = genai.GenerativeModel("gemini-2.0-flash")
        full_prompt = f"{prompt}\n\nLanguage: {lang}\nUser said: {message}"
        response = model.generate_content(full_prompt)
        return response.text.strip()
    except Exception as e:
        print("Gemini error:", e)
        return "Sorry, I'm having trouble replying right now."

# ==== VERIFY WEBHOOK ====
@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("✅ Webhook verified successfully")
        return challenge, 200
    else:
        return "Verification token mismatch", 403

# ==== HANDLE MESSAGES ====
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if data.get("object") == "page":
        for entry in data.get("entry", []):
            page_id = str(entry.get("id"))
            for event in entry.get("messaging", []):
                if "message" in event and "text" in event["message"]:
                    sender_id = event["sender"]["id"]
                    msg = event["message"]["text"].strip()

                    mode = detect_mode(msg)
                    config = PAGE_CONFIG[page_id]
                    gemini_key = config["gemini"]

                    # BUY MODE
                    if mode == "buy_product":
                        reply = (f"🛍️ You can explore Heaven products here:\n"
                                 f"{config['store']}\n\nWould you like me to suggest a few items?")
                    else:
                        reply = generate_reply(msg, gemini_key, AI_COMMANDS["chat_mode"]["prompt"])

                    send_message(sender_id, reply, page_id)
    return "OK", 200

@app.route("/", methods=["GET"])
def home():
    return "✅ HeavenBot Multi-Page AI Active (Psychologist + Sales Assistant)"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🚀 Webhook running on port {port}")
    serve(app, host="0.0.0.0", port=port)
