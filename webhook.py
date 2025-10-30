from flask import Flask, request
import requests, os
from dotenv import load_dotenv
from openpyxl import load_workbook
from langdetect import detect
import google.generativeai as genai
from waitress import serve

load_dotenv()
app = Flask(__name__)
@app.route('/test', methods=['GET'])
def test_home():
    return '✅ HeavenBot Multi-Page AI Active with Menu & Smart Modes', 200


# ====== CONFIG ======
VERIFY_TOKEN = "123abc"
PAGE_CONFIG = {}
MESSAGE_MEMORY = {}
AI_COMMANDS = {}

# ====== LOAD PAGE CONFIG ======
def load_page_config():
    wb = load_workbook("pages_config.xlsx", read_only=True)
    ws = wb.active
    for row in ws.iter_rows(min_row=2, values_only=True):
        page_name, page_id, token, gemini_key, excel_path = row
        if page_id:
            PAGE_CONFIG[str(page_id)] = {
                "token": token,
                "gemini": gemini_key,
                "excel": excel_path
            }

# ====== LOAD AI COMMAND CONFIG ======
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

# ====== SEND MESSAGE ======
def send_message(recipient_id, text, page_id):
    token = PAGE_CONFIG[str(page_id)]["token"]
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={token}"
    payload = {"recipient": {"id": recipient_id}, "message": {"text": text}}
    requests.post(url, json=payload)

# ====== FIND LINK FOR PRODUCT ======
def find_product_link(message, excel_path):
    try:
        wb = load_workbook(excel_path, read_only=True)
        ws = wb.active
        matches = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            desc, link = row
            if desc and link and str(desc).lower() in message.lower():
                matches.append(f"{desc}: {link}")
        if not matches:
            # Fuzzy matching (contains keyword)
            for row in ws.iter_rows(min_row=2, values_only=True):
                desc, link = row
                if desc and link and any(word in str(desc).lower() for word in message.lower().split()):
                    matches.append(f"{desc}: {link}")
        if matches:
            if len(matches) > 2:
                matches = matches[:2]
            return "\n".join(matches)
    except Exception as e:
        print("Excel read error:", e)
    return None

# ====== GEMINI RESPONSE ======
def generate_reply(message, api_key, custom_prompt=""):
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        lang = detect(message)
        prompt = custom_prompt or f"You are HeavenBot. Reply in the same language as user ({lang}). Message: {message}"
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print("Gemini error:", e)
        return "Sorry, I'm having trouble replying right now."

# ====== SELECT MODE ======
def detect_mode(message):
    text = message.lower()
    for key, cmd in AI_COMMANDS.items():
        if any(k in text for k in cmd["trigger"]):
            return key
    return "chat_mode"

# ====== VERIFY TOKEN ======
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

# ====== HANDLE MESSAGES ======
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

                    # Init memory
                    if sender_id not in MESSAGE_MEMORY:
                        MESSAGE_MEMORY[sender_id] = []
                        # Send greeting menu
                        send_message(sender_id,
                            "👋 Welcome to HeavenBot!\nPlease choose an option:\n"
                            "1️⃣ Chat with us\n"
                            "2️⃣ I want to edit a Heaven photo\n"
                            "3️⃣ I want to buy a product\n\n"
                            "💬 (Just type your choice or describe directly!)",
                            page_id
                        )

                    MESSAGE_MEMORY[sender_id].append(user_msg)
                    if len(MESSAGE_MEMORY[sender_id]) > 2:
                        MESSAGE_MEMORY[sender_id].pop(0)

                    mode = detect_mode(user_msg)
                    config = PAGE_CONFIG[page_id]
                    reply = ""

                    if mode == "buy_product":
                        product_info = find_product_link(user_msg, config["excel"])
                        if product_info:
                            reply = f"Here are some matching products:\n{product_info}\nWould you like to see more?"
                        else:
                            reply = "I couldn't find that quote yet. Let's chat about it!"
                    elif mode == "image_edit":
                        reply = ("Please send the original photo 📸 and a short description of the person "
                                 "(especially if there are multiple people). I’ll create a Heaven-style photo 🌤️.")
                    else:
                        reply = generate_reply(user_msg, config["gemini"], AI_COMMANDS.get(mode, {}).get("prompt", ""))

                    send_message(sender_id, reply, page_id)
    return "OK", 200

@app.route("/", methods=["GET"])
def home():
    return "✅ HeavenBot Multi-Page AI Active with Menu & Smart Modes"

# ====== RUN SERVER ======
if __name__ == '__main__':
    from waitress import serve
    import os

    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Webhook server starting on port {port} ...")
    serve(app, host='0.0.0.0', port=port)
