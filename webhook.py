from flask import Flask, request
import requests, os
from dotenv import load_dotenv
from openpyxl import load_workbook
from langdetect import detect
import google.generativeai as genai
from waitress import serve

# =========================
# INITIAL SETUP
# =========================
load_dotenv()
app = Flask(__name__)

VERIFY_TOKEN = "123abc"
PAGE_CONFIG = {}
AI_COMMANDS = {}

# =========================
# LOAD CONFIG FROM EXCEL
# =========================
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

load_page_config()

# =========================
# LIST OF TRIGGERS (mua hàng)
# =========================
BUY_KEYWORDS = [
    # lower
    "buy", "purchase", "order", "shop", "shopping", "store", "gift", "shirt", "tshirt", "hoodie",
    "buy something", "want to buy", "buy a product", "buy product", "i want to order",
    "link shop", "link store", "t-shirt", "product", "item", "merch", "sale",
    "clothes", "apparel", "quote", "heaven gift", "heaven store", "heaven shirt",
    # upper and title case
    "Buy", "Purchase", "Order", "Shop", "Shopping", "Store", "Gift", "Shirt", "Tshirt", "Hoodie",
    "Buy something", "Want to buy", "Buy a product", "Buy product", "I want to order",
    "Link shop", "Link store", "T-Shirt", "Product", "Item", "Merch", "Sale",
    "Clothes", "Apparel", "Quote", "Heaven Gift", "Heaven Store", "Heaven Shirt"
]

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
    for keyword in BUY_KEYWORDS:
        if keyword in message:
            return "buy"
    return "chat"

# =========================
# GEMINI GENERATION
# =========================
def generate_reply(message, api_key, role="chat"):
    try:
        genai.configure(api_key=api_key)
        lang = detect(message)
        model = genai.GenerativeModel("gemini-2.0-flash")

        if role == "chat":
            system_prompt = (
                "You are a compassionate Heaven psychologist assistant. "
                "Speak softly, kindly, and comfort people who miss their loved ones. "
                "Use emotional intelligence and reply in the same language as user. "
                "Avoid sales talk unless user asks about store or product."
            )
        else:
            system_prompt = (
                "You are a Heaven Store sales assistant. Be warm, kind and friendly. "
                "If asked about products, explain briefly and direct the user to the Heaven store. "
                "Always reply in the same language as user."
            )

        full_prompt = f"{system_prompt}\n\nUser message: {message}\nLanguage: {lang}"
        response = model.generate_content(full_prompt)
        return response.text.strip()

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
                    config = PAGE_CONFIG[page_id]
                    gemini_key = config["gemini"]

                    # ---- Nếu là mua hàng ----
                    if mode == "buy":
                        store_link = config.get("store", "")
                        if store_link:
                            reply = (
                                f"🛒 You can explore Heaven products here:\n"
                                f"{store_link}\n\n"
                                "Would you like me to suggest a few beautiful memorial gifts?"
                            )
                        else:
                            reply = "🛍️ Our Heaven store link is not configured yet."
                    else:
                        # ---- Nếu là trò chuyện ----
                        reply = generate_reply(message, gemini_key, role="chat")

                    send_message(sender_id, reply, page_id)
    return "OK", 200

# =========================
# HOME PAGE
# =========================
@app.route("/", methods=["GET"])
def home():
    return "✅ HeavenBot Active – Comfort & Sales AI Ready", 200

# =========================
# START SERVER
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🚀 Webhook running on port {port}")
    serve(app, host="0.0.0.0", port=port)
