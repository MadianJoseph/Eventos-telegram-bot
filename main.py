import time
import requests
import threading
import os
from datetime import datetime
import pytz

from flask import Flask
from playwright.sync_api import sync_playwright


# ================= CONFIG =================
URL_LOGIN = "https://eventossistema.com.mx/login.html"
URL_EVENTS = "https://eventossistema.com.mx/confirmaciones/default.html"

CHECK_INTERVAL = 60  # refresco cada 60s
NO_EVENTS_TEXT = "No hay eventos disponibles por el momento."

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

sent_today_start = False
sent_today_stop = False


# ================= TELEGRAM =================
def send(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg}, timeout=10)


# ================= HORARIO =================
def working_hours():
    now = datetime.now(TZ)
    return 6 <= now.hour < 24


# ================= FORMATEAR =================
def format_event(text):
    upper = text.upper()

    header = ""

    if any(p in upper for p in IMPORTANT_PLACES):
        header += "🔥 IMPORTANTE / CERCA\n"

    if "GIRA" in upper:
        header += "⚠️ POSIBLE GIRA / LEJOS\n"

    return f"🚨 ¡HAY EVENTOS DISPONIBLES!\n\n{header}{text}"


# ================= BOT LOOP =================
def bot_loop():
    global sent_today_start, sent_today_stop

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        logged = False

        while True:
            now = datetime.now(TZ)

            # ===== mensajes diarios =====
            if now.hour == 6 and not sent_today_start:
                send("🌅 Bot activado. Iniciando monitoreo.")
                sent_today_start = True
                sent_today_stop = False

            if now.hour == 0 and not sent_today_stop:
                send("🌙 Bot dormido hasta las 6am.")
                sent_today_stop = True
                sent_today_start = False

            if not working_hours():
                time.sleep(60)
                continue

            try:
                # ================= LOGIN SOLO SI ES NECESARIO =================
                if not logged:
                    send("🔐 Iniciando sesión...")

                    page.goto(URL_LOGIN)
                    page.wait_for_load_state("networkidle")

                    page.get_by_placeholder("Usuario").fill(USER)
                    page.get_by_placeholder("Contraseña").fill(PASSWORD)
                    page.get_by_role("button", name="Iniciar sesión").click()

                    page.wait_for_timeout(4000)

                    page.goto(URL_EVENTS)
                    logged = True

                # ================= REFRESH =================
                page.reload()
                page.wait_for_timeout(3000)

                content = page.inner_text("body")

                # ================= SESIÓN EXPIRADA =================
                if "INICIAR SESIÓN" in content.upper():
                    send("🔄 Sesión expirada. Reintentando login...")
                    logged = False
                    continue

                # ================= EVENTOS =================
                if NO_EVENTS_TEXT not in content:
                    send(format_event(content))

            except Exception as e:
                send(f"⚠️ Error: {e}")
                logged = False

            time.sleep(CHECK_INTERVAL)


# ================= FLASK (Render necesita puerto abierto) =================
@app.route("/")
def home():
    return "Bot activo"


if __name__ == "__main__":
    def start_bot():
        threading.Thread(target=bot_loop, daemon=True).start()

    threading.Timer(3, start_bot).start()

    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)), use_reloader=False)
