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

IMPORTANT_PLACES = ["ESTADIO GNP", "PALACIO DE LOS DEPORTES", "AUTODROMO HERMANOS RODRIGUEZ", "ESTADIO HARP HELU"]

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

# ================= BOT LOOP =================
def bot_loop():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-setuid-sandbox"]
        )
        
        # Forzamos un viewport real para evitar bloqueos
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 720}
        )
        page = context.new_page()
        page.set_default_timeout(60000) # 60 segundos máximo
        logged = False

        while True:
            try:
                if not working_hours():
                    time.sleep(60)
                    continue

                if not logged:
                    send("🔐 Paso 1: Cargando página de login...")
                    try:
                        # 'commit' es la forma más rápida de avanzar
                        page.goto(URL_LOGIN, wait_until="commit")
                        page.wait_for_timeout(5000) # Espera manual de seguridad

                        send("🔐 Paso 2: Llenando credenciales...")
                        page.get_by_placeholder("Usuario").fill(USER)
                        page.get_by_placeholder("Contraseña").fill(PASSWORD)
                        
                        send("🔐 Paso 3: Clic en Iniciar Sesión...")
                        page.get_by_role("button", name="Iniciar sesión").click()
                        
                        # Esperamos a ver si cambia la URL o aparece un error
                        page.wait_for_timeout(10000) 

                        if URL_LOGIN in page.url:
                            # Intentamos ver si hay un mensaje de error visible en la página
                            send("❌ Error: Login rechazado (posible usuario/pass incorrecto).")
                            time.sleep(180)
                            continue

                        send("✅ Sesión exitosa. Accediendo a eventos...")
                        page.goto(URL_EVENTS, wait_until="commit")
                        logged = True
                    except Exception as e:
                        send(f"⚠️ Error en proceso de login: {str(e)[:100]}")
                        time.sleep(30)
                        continue

                # MONITOREO
                page.reload(wait_until="commit")
                page.wait_for_timeout(5000)
                content = page.inner_text("body")

                if "INICIAR SESIÓN" in content.upper() or "LOGIN" in content.upper():
                    send("🔄 Sesión perdida. Reconectando...")
                    logged = False
                    continue

                if NO_EVENTS_TEXT not in content and len(content.strip()) > 30:
                    send(f"🚨 ¡EVENTOS!:\n\n{content[:1000]}")
                    time.sleep(600) # Pausa larga si detecta algo

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
    
