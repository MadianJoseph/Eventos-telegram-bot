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

# Variables de entorno extraídas de la configuración de Render
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

    # Se agregan argumentos necesarios para entornos Linux/Docker en la nube
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-setuid-sandbox"]
        )
        
        # Se añade un User Agent real para evitar ser detectado como bot
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        logged = False

        while True:
            try:
                now = datetime.now(TZ)

                # Mensajes diarios de estado
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

                # LOGIN
                if not logged:
                    send("🔐 Intentando iniciar sesión...")
                    page.goto(URL_LOGIN, wait_until="networkidle")

                    page.get_by_placeholder("Usuario").fill(USER)
                    page.get_by_placeholder("Contraseña").fill(PASSWORD)
                    page.get_by_role("button", name="Iniciar sesión").click()

                    page.wait_for_timeout(5000) # Espera a que cargue el dashboard
                    page.goto(URL_EVENTS, wait_until="networkidle")
                    logged = True

                # REFRESH Y MONITOREO
                page.reload(wait_until="networkidle")
                page.wait_for_timeout(3000)

                content = page.inner_text("body")

                # Verificar si la sesión expiró
                if "INICIAR SESIÓN" in content.upper() or "LOGIN" in content.upper():
                    send("🔄 Sesión expirada. Reintentando login...")
                    logged = False
                    continue

                # Analizar contenido de eventos
                if NO_EVENTS_TEXT not in content and len(content.strip()) > 50:
                    # Filtramos para que no mande mensajes vacíos o errores cortos
                    send(format_event(content[:1000])) # Limitamos caracteres para Telegram

            except Exception as e:
                print(f"Error en el bucle: {e}")
                # No enviamos mensaje a Telegram por cada error para evitar spam si falla el internet
                logged = False
                time.sleep(10)

            time.sleep(CHECK_INTERVAL)

# ================= FLASK =================
@app.route("/")
def home():
    return "Bot de Eventos: Ejecutándose correctamente."

if __name__ == "__main__":
    # Inicia el bot en un hilo separado para que Flask pueda responder a Render
    def start_bot():
        bot_loop()

    threading.Thread(target=start_bot, daemon=True).start()

    # Render usa la variable de entorno PORT
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, use_reloader=False)
    
