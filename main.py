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

CHECK_INTERVAL = 60 # Cambiado a 60 segundos por seguridad

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
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except Exception as e:
        print(f"Error enviando a Telegram: {e}")

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
        days = (event_date.date() - datetime.now(TZ).date()).days
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

# ================= FUNCIÓN DE LOGIN =================
def do_login(page):
    print("Iniciando sesión...")
    page.goto(URL_LOGIN)
    page.wait_for_load_state("networkidle")
    page.get_by_placeholder("Usuario").fill(USER)
    page.get_by_placeholder("Contraseña").fill(PASSWORD)
    page.get_by_role("button", name="Iniciar sesión").click()
    page.wait_for_timeout(5000) # Espera a que redireccione

# ================= PLAYWRIGHT BOT =================
def bot_loop():
    send("🤖 Bot iniciado y monitoreando (Modo Optimizado)")

    with sync_playwright() as p:
        # Importante: Chromium en modo headless para Render
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = context.new_page()

        # Login inicial
        try:
            do_login(page)
        except Exception as e:
            send(f"⚠️ Error en login inicial: {e}")

        while True:
            try:
                now = datetime.now(TZ)

                # Mensajes de estado diarios
                if now.hour == 6 and now.minute == 0:
                    send("🌅 Iniciando monitoreo del día")
                if now.hour == 0 and now.minute == 0:
                    send("🌙 Bot desactivado por horario (Duerme)")

                if not working_hours():
                    time.sleep(60)
                    continue

                # Ir a la página de eventos directamente
                page.goto(URL_EVENTS)
                page.wait_for_load_state("networkidle")

                # RE-LOGIN AUTOMÁTICO: Si la página nos regresó al login o pide usuario
                if page.get_by_placeholder("Usuario").is_visible():
                    print("Sesión cerrada. Re-logueando...")
                    do_login(page)
                    page.goto(URL_EVENTS)

                page.wait_for_timeout(3000)
                content = page.inner_text("body")

                if "EVENTOS DISPONIBLES" in content:
                    events = content.split("EVENTOS DISPONIBLES")
                    raw = events[1].strip()

                    # Solo si hay texto después de "EVENTOS DISPONIBLES"
                    if raw and raw not in last_events:
                        last_events.add(raw)
                        send(format_event(raw))
                
            except Exception as e:
                print(f"Error en el loop: {e}")
                # No enviamos error a Telegram cada 60s para no hacer spam si cae el sitio
                # Solo si es un error crítico podrías habilitarlo

            time.sleep(CHECK_INTERVAL)

# ================= FLASK =================
@app.route("/")
def home():
    return "Bot activo y funcionando"

if __name__ == "__main__":
    # Hilo secundario para el bot
    threading.Thread(target=bot_loop, daemon=True).start()
    # Puerto dinámico para Render
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
                    
