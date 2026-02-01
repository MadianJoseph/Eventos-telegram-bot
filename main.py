import time
import requests
from bs4 import BeautifulSoup
from flask import Flask
import threading
import os

# ================== CONFIG ==================
URL = "https://eventossistema.com.mx/confirmaciones/default.html"
CHECK_INTERVAL = 45  # segundos

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

paused = False
last_content = None

app = Flask(__name__)

# ================== TELEGRAM ==================
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": msg}
    requests.post(url, data=data, timeout=10)

# ================== CHECK PAGE ==================
def check_page():
    global last_content, paused

    send_telegram("🤖 Bot activo en Render")

    while True:
        if not paused:
            try:
                r = requests.get(URL, timeout=20)
                soup = BeautifulSoup(r.text, "html.parser")

                section = soup.get_text()

                if last_content and section != last_content:
                    send_telegram("🚨 ¡CAMBIO DETECTADO!\nHay un nuevo evento disponible.")
                
                last_content = section

            except Exception as e:
                send_telegram(f"⚠️ Error al revisar página:\n{e}")

        time.sleep(CHECK_INTERVAL)

# ================== TELEGRAM COMMANDS ==================
def telegram_commands():
    offset = -1
print("🤖 Escuchando comandos de Telegram...")

    while True:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        params = {"timeout": 100, "offset": offset}
        r = requests.get(url, params=params, timeout=120).json()

        for update in r.get("result", []):
            offset = update["update_id"] + 1
            text = update.get("message", {}).get("text", "")

            if text == "/status":
                send_telegram("✅ Bot activo" if not paused else "⏸ Bot en pausa")

            elif text == "/pause":
                paused = True
                send_telegram("⏸ Bot pausado")

            elif text == "/resume":
                paused = False
                send_telegram("▶️ Bot reanudado")

            elif text == "/test":
                send_telegram("🧪 Mensaje de prueba correcto")

# ================== FLASK ==================
@app.route("/")
def home():
    return "Bot activo"

if __name__ == "__main__":
    threading.Thread(target=check_page).start()
    threading.Thread(target=telegram_commands).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
