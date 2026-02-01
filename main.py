import time
import requests
import threading
import os
from datetime import datetime, timedelta
import pytz

from flask import Flask
from playwright.sync_api import sync_playwright

# ================= CONFIG =================
URL_LOGIN = "https://eventossistema.com.mx/login.html"
URL_EVENTS = "https://eventossistema.com.mx/confirmaciones/default.html"

CHECK_INTERVAL = 30

TZ = pytz.timezone("America/Mexico_City")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

USER = os.getenv("WEB_USER")
PASSWORD = os.getenv("WEB_PASS")

IMPORTANT_PLACES = [
    "ESTADIO GNP",
    "PALACIO DE LOS DEPORTES",
    "AUTODROMO HERMANOS RODRIGUEZ",
    "ESTADIO HARP HELU",
]

app = Flask(__name__)
last_events = set()


# ================= TELEGRAM =================
def send(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg})


# ================= HORARIO =================
def working_hours():
    now = datetime.now(TZ)
    return 6 <= now.hour < 24


# ================= FORMATEAR EVENTO =================
def format_event(text):
    lines = text.upper()

    important = any(p in lines for p in IMPORTANT_PLACES)
    far = "GIRA" in lines

    date_line = next((l for l in text.split("\n") if "/" in l), "")
    cancel_msg = ""

    try:
        event_date = datetime.strptime(date_line[:10], "%d/%m/%Y")
        days = (event_date.date() - datetime.now().date()).days
        if days >= 4:
            cancel_msg = "✅ Se puede cancelar\n"
    except:
        pass

    header = ""
    if important:
        header = "🔥 IMPORTANTE - CERCA\n"
    elif far:
        header = "⚠️ POSIBLE GIRA / LEJOS\n"

    return f"🚨 ¡NUEVO EVENTO DISPONIBLE!\n\n{header}{cancel_msg}{text}"


# ================= PLAYWRIGHT =================
def bot_loop():
    send("🤖 Bot iniciado correctamente")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        while True:
            try:
                now = datetime.now(TZ)

                # mensajes diarios
                if now.hour == 6 and now.minute == 0:
                    send("🌅 Iniciando monitoreo del día")

                if now.hour == 0 and now.minute == 0:
                    send("🌙 Bot desactivado por horario")

                if not working_hours():
                    time.sleep(60)
                    continue

                # LOGIN

                page.goto(URL_EVENTS)
                page.wait_for_load_state("networkidle")

                page.get_by_placeholder("Usuario").fill(USER)
                page.get_by_placeholder("Contraseña").fill(PASSWORD)

                page.get_by_role("button", name="Iniciar sesión").click()

                page.wait_for_timeout(4000)
                # IR A EVENTOS
                page.goto(URL_EVENTS)
                page.wait_for_timeout(3000)

                content = page.inner_text("body")

                events = content.split("EVENTOS DISPONIBLES")

                if len(events) > 1:
                    raw = events[1].strip()

                    if True:
                        last_events.add(raw)
                        send(format_event(raw))

            except Exception as e:
                send(f"⚠️ Error: {e}")

            time.sleep(CHECK_INTERVAL)


# ================= FLASK =================
@app.route("/")
def home():
    return "Bot activo"


if __name__ == "__main__":
    threading.Thread(target=bot_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
