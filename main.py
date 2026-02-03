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
            args=[
                "--no-sandbox", 
                "--disable-dev-shm-usage", 
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled" # Oculta que es un bot
            ]
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
                    send("🔐 Intentando login con técnica de simulación humana...")
                    # Vamos a la página y esperamos solo lo esencial
                    page.goto(URL_LOGIN, wait_until="commit")
                    page.wait_for_timeout(10000) # Espera 10 seg reales a que carguen los inputs

                    try:
                        # En lugar de buscar por placeholder, hacemos click en el centro de la pantalla
                        # y usamos TAB para navegar, esto salta bloqueos de selectores
                        page.mouse.click(640, 360) 
                        
                        # Escribimos el usuario "a ciegas" por si el selector falla
                        # pero intentamos el selector primero por si acaso
                        fields = page.locator("input")
                        if fields.count() > 0:
                            fields.first.fill(USER)
                            page.keyboard.press("Tab")
                            page.keyboard.type(PASSWORD)
                            page.keyboard.press("Enter")
                        else:
                            # Si no hay inputs detectados, intentamos modo ultra-ciego
                            page.keyboard.press("Tab")
                            page.keyboard.type(USER)
                            page.keyboard.press("Tab")
                            page.keyboard.type(PASSWORD)
                            page.keyboard.press("Enter")

                        send("⏳ Esperando respuesta del servidor...")
                        page.wait_for_timeout(12000) 

                        if URL_LOGIN in page.url:
                            send("❌ Seguimos en Login. Posible bloqueo de IP o datos mal ingresados.")
                            # Intentamos ir directo a la URL de eventos por si el login fue silencioso
                            page.goto(URL_EVENTS, wait_until="commit")
                        else:
                            send("✅ ¡Parece que entramos!")
                            logged = True

                    except Exception as e:
                        send(f"⚠️ Error táctico: {str(e)[:50]}")
                        time.sleep(60)
                        continue

                # MONITOREO
                page.goto(URL_EVENTS, wait_until="commit")
                page.wait_for_timeout(5000)
                content = page.inner_text("body")

                if "INICIAR SESIÓN" in content.upper() or "LOGIN" in content.upper():
                    logged = False
                    continue

                if NO_EVENTS_TEXT not in content and len(content.strip()) > 30:
                    send(f"🚨 EVENTO:\n\n{content[:1000]}")
                    time.sleep(600)

            except Exception as e:
                print(f"Error: {e}")
                logged = False
                time.sleep(30)

            time.sleep(CHECK_INTERVAL)

@app.route("/")
def home(): return "Bot Online"

if __name__ == "__main__":
    threading.Thread(target=bot_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, use_reloader=False)
    
