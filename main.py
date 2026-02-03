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

CHECK_INTERVAL = 60 
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

def send(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg}, timeout=10)
    except: pass

def working_hours():
    now = datetime.now(TZ)
    return 6 <= now.hour < 24

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
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-setuid-sandbox"]
        )
        
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        # Aumentamos el timeout global a 90 segundos
        page.set_default_timeout(90000)
        logged = False

        while True:
            try:
                now = datetime.now(TZ)

                if now.hour == 6 and not sent_today_start:
                    send("🌅 Bot activado. Iniciando monitoreo.")
                    sent_today_start, sent_today_stop = True, False

                if now.hour == 0 and not sent_today_stop:
                    send("🌙 Bot dormido hasta las 6am.")
                    sent_today_stop, sent_today_start = True, False

                if not working_hours():
                    time.sleep(60)
                    continue

                if not logged:
                    send("🔐 Intentando iniciar sesión (espera extendida)...")
                    try:
                        # Usamos 'domcontentloaded' para que sea más rápido y menos propenso a timeouts
                        page.goto(URL_LOGIN, wait_until="domcontentloaded")
                        
                        page.get_by_placeholder("Usuario").fill(USER)
                        page.get_by_placeholder("Contraseña").fill(PASSWORD)
                        
                        # Clic y esperar a que cambie la URL
                        page.get_by_role("button", name="Iniciar sesión").click()
                        page.wait_for_timeout(10000) 

                        if page.url == URL_LOGIN:
                            send("❌ Login fallido. Revisa credenciales.")
                            time.sleep(120) 
                            continue

                        page.goto(URL_EVENTS, wait_until="domcontentloaded")
                        send("✅ Sesión iniciada con éxito.")
                        logged = True
                    except Exception as login_err:
                        print(f"Error login: {login_err}")
                        time.sleep(30)
                        continue

                # MONITOREO
                page.reload(wait_until="domcontentloaded")
                page.wait_for_timeout(5000)

                content = page.inner_text("body")

                if "INICIAR SESIÓN" in content.upper():
                    logged = False
                    continue

                if NO_EVENTS_TEXT not in content and len(content.strip()) > 30:
                    send(format_event(content[:1200]))
                    time.sleep(300) 

            except Exception as e:
                print(f"Error: {e}")
                logged = False
                time.sleep(30)

            time.sleep(CHECK_INTERVAL)

@app.route("/")
def home():
    return "Bot Online"

if __name__ == "__main__":
    threading.Thread(target=bot_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, use_reloader=False)
                        
