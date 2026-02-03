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

CHECK_INTERVAL = 300 # Recomendado 5 min para evitar bloqueos
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
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg}, timeout=10)
    except: pass

def working_hours():
    now = datetime.now(TZ)
    return 6 <= now.hour < 24

def clean_event_text(text):
    if "EVENTOS CONFIRMADOS" in text:
        text = text.split("EVENTOS CONFIRMADOS")[0]
    if "EVENTOS DISPONIBLES" in text:
        parts = text.split("EVENTOS DISPONIBLES")
        text = "🚨 **EVENTOS DISPONIBLES** 🚨\n" + parts[-1]
    return text.strip()

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
        page.set_default_timeout(80000)
        logged = False

        while True:
            try:
                if not working_hours():
                    time.sleep(60)
                    continue

                if not logged:
                    page.goto(URL_LOGIN, wait_until="networkidle")
                    page.wait_for_timeout(5000)
                    
                    # Limpiamos campos antes de escribir
                    page.keyboard.press("Control+A")
                    page.keyboard.press("Backspace")
                    
                    # Escribimos con delay para parecer humanos
                    page.keyboard.type(USER, delay=150)
                    page.keyboard.press("Tab")
                    page.keyboard.type(PASSWORD, delay=150)
                    page.keyboard.press("Enter")
                    
                    # ESPERA CRÍTICA: Dejamos que el sistema procese el login
                    page.wait_for_url("**/default.html", timeout=20000) 
                    send("✅ Login verificado. Entrando al panel...")
                    logged = True

                # --- MONITOREO ---
                page.goto(URL_EVENTS, wait_until="domcontentloaded")
                page.wait_for_timeout(5000)
                content = page.inner_text("body")

                # Si detecta palabras de login, es que nos sacó
                if "INGRESE SUS CREDENCIALES" in content.upper() or "ID USUARIO" in content.upper():
                    logged = False
                    continue

                if NO_EVENTS_TEXT not in content and len(content.strip()) > 50:
                    mensaje_limpio = clean_event_text(content)
                    # Solo enviamos si el mensaje contiene algo más que el título
                    if len(mensaje_limpio) > 40:
                        send(mensaje_limpio)
                
                time.sleep(CHECK_INTERVAL)

            except Exception as e:
                print(f"Reintentando por error: {e}")
                logged = False # Forzamos re-login en caso de cualquier error
                time.sleep(30)

@app.route("/")
def home(): return "Bot Online"

if __name__ == "__main__":
    threading.Thread(target=bot_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, use_reloader=False)
    
