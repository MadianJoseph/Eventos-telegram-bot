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

# [span_0](start_span)Variables de entorno de Render[span_0](end_span)
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
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print(f"Error: Configuración de Telegram incompleta. Msg: {msg}")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg}, timeout=10)
    except Exception as e:
        print(f"Error enviando Telegram: {e}")

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
        # Lanzamiento optimizado para Render
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-setuid-sandbox"]
        )
        
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        logged = False

        while True:
            try:
                now = datetime.now(TZ)

                # Control de mensajes diarios
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

                # ================= PROCESO DE LOGIN =================
                if not logged:
                    send("🔐 Intentando iniciar sesión...")
                    try:
                        page.goto(URL_LOGIN, wait_until="networkidle", timeout=60000)

                        page.get_by_placeholder("Usuario").fill(USER)
                        page.get_by_placeholder("Contraseña").fill(PASSWORD)
                        
                        # Clic y espera de navegación
                        page.get_by_role("button", name="Iniciar sesión").click()
                        page.wait_for_timeout(8000) 

                        # Verificación de éxito de login
                        if page.url == URL_LOGIN:
                            send("❌ Error: Login fallido. Revisa credenciales en Render.")
                            time.sleep(300) 
                            continue

                        page.goto(URL_EVENTS, wait_until="networkidle")
                        send("✅ Sesión iniciada. Monitoreando eventos...")
                        logged = True
                    except Exception as login_err:
                        send(f"⚠️ Error en login: {str(login_err)[:100]}")
                        logged = False
                        time.sleep(60)
                        continue

                # ================= MONITOREO =================
                page.reload(wait_until="networkidle")
                page.wait_for_timeout(4000)

                content = page.inner_text("body")

                # Sesión expirada
                if "INICIAR SESIÓN" in content.upper() or "LOGIN" in content.upper():
                    send("🔄 Sesión expirada. Reintentando...")
                    logged = False
                    continue

                # Detección de eventos
                if NO_EVENTS_TEXT not in content and len(content.strip()) > 30:
                    send(format_event(content[:1200]))
                    # Espera más larga si hay eventos para no saturar Telegram
                    time.sleep(300) 

            except Exception as e:
                print(f"Error en bucle: {e}")
                logged = False
                time.sleep(20)

            time.sleep(CHECK_INTERVAL)

# ================= FLASK =================
@app.route("/")
def home():
    return "Bot de Eventos: Online"

if __name__ == "__main__":
    def start_bot():
        bot_loop()

    # Hilo secundario para el bot
    threading.Thread(target=start_bot, daemon=True).start()

    # Puerto dinámico de Render
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, use_reloader=False)
                
