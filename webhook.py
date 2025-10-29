from flask import Flask, request
import requests, os
from dotenv import load_dotenv
from openpyxl import load_workbook
import google.generativeai as genai

load_dotenv()
app = Flask(__name__)

# --- Cache tạm dữ liệu để tránh đọc lại Excel nhiều lần ---
PAGE_CONFIG = {}
MESSAGE_MEMORY = {}

# --- Đọc file cấu hình pages_config.xlsx ---
def load_page_config():
    wb = load_workbook("pages_config.xlsx", read_only=True)
    ws = wb.active
    for row in ws.iter_rows(min_row=2, values_only=True):
        page_name, page_id, token, gemini_key, excel_path = row
        PAGE_CONFIG[str(page_id)] = {
            "token": token,
            "gemini": gemini_key,
            "excel": excel_path
        }

load_page_config()


# --- Kiểm tra tin nhắn vô nghĩa ---
def is_meaningless(msg):
    return not any(ch.isalnum() for ch in msg) or len(msg.strip()) < 2


# --- Tìm link phù hợp trong file Excel ---
def find_link(message, excel_path):
    try:
        wb = load_workbook(excel_path, read_only=True)
        ws = wb.active
        for row in ws.iter_rows(min_row=2, values_only=True):
            desc, link = row
            if desc and str(desc).lower() in message.lower():
                return f"{desc}: {link}"
    except:
        pass
    return None


# --- Sinh trả lời từ Gemini ---
def generate_reply(message, api_key):
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        prompt = f"Reply naturally in English: {message}"
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print("Gemini error:", e)
        return "Sorry, I'm having trouble replying right now."


# --- Gửi tin nhắn về Facebook ---
def send_message(recipient_id, text, page_id):
    token = PAGE_CONFIG[str(page_id)]["token"]
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={token}"
    payload = {"recipient": {"id": recipient_id}, "message": {"text": text}}
    requests.post(url, json=payload)


# --- Nhận tin nhắn ---
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    if data.get("object") == "page":
        for entry in data.get("entry", []):
            page_id = str(entry.get("id"))
            for event in entry.get("messaging", []):
                if "message" in event and "text" in event["message"]:
                    sender_id = event["sender"]["id"]
                    user_msg = event["message"]["text"]

                    # --- Bộ nhớ ngắn 2 tin ---
                    if sender_id not in MESSAGE_MEMORY:
                        MESSAGE_MEMORY[sender_id] = []
                    MESSAGE_MEMORY[sender_id].append(user_msg)
                    if len(MESSAGE_MEMORY[sender_id]) > 2:
                        MESSAGE_MEMORY[sender_id].pop(0)

                    # --- Lọc vô nghĩa ---
                    if is_meaningless(user_msg):
                        memory = MESSAGE_MEMORY[sender_id]
                        if len(memory) == 1:
                            send_message(sender_id, "Hello! Nice to chat with you.", page_id)
                        continue

                    # --- Kiểm tra Excel ---
                    excel_path = PAGE_CONFIG[page_id]["excel"]
                    reply = find_link(user_msg, excel_path)
                    if not reply:
                        reply = generate_reply(user_msg, PAGE_CONFIG[page_id]["gemini"])

                    send_message(sender_id, reply, page_id)
    return "OK", 200


@app.route("/", methods=["GET"])
def home():
    return "✅ HeavenBot multi-page AI active!"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
