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

# CAMBIO: 60 segundos para que sea cada minuto
CHECK_INTERVAL = 60 
NO_EVENTS_TEXT = "No hay eventos disponibles por el momento."
TZ = pytz.timezone("America/Mexico_City")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
USER = os.getenv("WEB_USER")
PASSWORD = os.getenv("WEB_PASS")

app = Flask(__name__)

def send(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        # Añadimos parse_mode Markdown por si quieres usar negritas
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def working_hours():
    now = datetime.now(TZ)
    return 6 <= now.hour < 24

def clean_event_text(text):
    resultado = text
    if "EVENTOS CONFIRMADOS" in text:
        resultado = text.split("EVENTOS CONFIRMADOS")[0]
    
    if "EVENTOS DISPONIBLES" in resultado:
        parts = resultado.split("EVENTOS DISPONIBLES")
        resultado = "*🚨 NUEVOS EVENTOS DETECTADOS 🚨*\n" + parts[-1]
    
    # Añadimos la hora para confirmar que es un reporte nuevo
    hora_actual = datetime.now(TZ).strftime("%H:%M:%S")
    return f"{resultado.strip()}\n\n🕒 _Actualizado: {hora_actual}_"

# ================= BOT LOOP =================
def bot_loop():
    with sync_playwright() as p:
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
                if not working_hours():
                    time.sleep(30)
                    continue

                if not logged:
                    page.goto(URL_LOGIN, wait_until="networkidle")
                    page.wait_for_timeout(4000)
                    
                    page.keyboard.press("Tab")
                    page.keyboard.type(USER, delay=100)
                    page.keyboard.press("Tab")
                    page.keyboard.type(PASSWORD, delay=100)
                    page.keyboard.press("Enter")
                    
                    page.wait_for_timeout(10000)
                    logged = True

                # --- MONITOREO ---
                page.goto(URL_EVENTS, wait_until="domcontentloaded")
                page.wait_for_timeout(5000)
                content = page.inner_text("body")

                # Si el sitio nos sacó al login
                if "ID USUARIO" in content.upper() or "INGRESE" in content.upper():
                    logged = False
                    continue

                # Si NO está el texto de "no hay eventos", significa que hay algo
                if NO_EVENTS_TEXT not in content and len(content.strip()) > 50:
                    mensaje = clean_event_text(content)
                    send(mensaje)
                else:
                    # Opcional: imprimir en consola de Render para saber que revisó
                    print(f"[{datetime.now(TZ)}] Revisión: Sin eventos nuevos.")

            except Exception as e:
                print(f"Error: {e}")
                logged = False
                time.sleep(20)

            # Espera exacta de 60 segundos
            time.sleep(CHECK_INTERVAL)

@app.route("/")
def home(): return "Bot Online - Reportando cada 60s"

if __name__ == "__main__":
    threading.Thread(target=bot_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, use_reloader=False)
    
