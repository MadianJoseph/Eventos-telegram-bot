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

CHECK_INTERVAL = 300 # 5 minutos
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
    # Lógica de recorte mejorada
    resultado = text
    if "EVENTOS CONFIRMADOS" in text:
        resultado = text.split("EVENTOS CONFIRMADOS")[0]
    
    if "EVENTOS DISPONIBLES" in resultado:
        parts = resultado.split("EVENTOS DISPONIBLES")
        resultado = "🚨 **NUEVOS EVENTOS** 🚨\n" + parts[-1]
    
    # Si el resultado es muy corto, devolvemos el original para no perder info
    return resultado.strip() if len(resultado.strip()) > 10 else text[:500]

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

        send("🤖 Bot Reiniciado: Iniciando ciclo de monitoreo...")

        while True:
            try:
                if not working_hours():
                    time.sleep(60)
                    continue

                if not logged:
                    page.goto(URL_LOGIN, wait_until="networkidle", timeout=60000)
                    page.wait_for_timeout(3000)
                    
                    # Login
                    page.keyboard.press("Tab")
                    page.keyboard.type(USER, delay=100)
                    page.keyboard.press("Tab")
                    page.keyboard.type(PASSWORD, delay=100)
                    page.keyboard.press("Enter")
                    
                    # Esperar cambio de página
                    page.wait_for_timeout(10000)
                    logged = True
                    send("🔑 Sesión iniciada correctamente.")

                # --- MONITOREO ---
                page.goto(URL_EVENTS, wait_until="domcontentloaded")
                page.wait_for_timeout(5000)
                content = page.inner_text("body")

                # Verificación de expulsión
                if "ID USUARIO" in content.upper() or "INGRESE" in content.upper():
                    logged = False
                    continue

                if NO_EVENTS_TEXT in content:
                    # Opcional: Descomenta la siguiente línea si quieres que te avise que NO hay nada
                    # send("pasa nada") 
                    pass
                elif len(content.strip()) > 50:
                    mensaje = clean_event_text(content)
                    send(mensaje)
                
                # Para depuración: imprimimos en consola de Render
                print(f"[{datetime.now(TZ)}] Ciclo completado sin eventos nuevos.")

            except Exception as e:
                print(f"Error detectado: {e}")
                # Si hay error, cerramos contexto para limpiar memoria
                logged = False
                time.sleep(60)

            time.sleep(CHECK_INTERVAL)

@app.route("/")
def home(): return "Bot Online"

if __name__ == "__main__":
    threading.Thread(target=bot_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, use_reloader=False)
    
