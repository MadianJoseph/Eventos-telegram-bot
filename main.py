import time
import requests
import threading
import os
from datetime import datetime, timedelta
import pytz
from flask import Flask
from playwright.sync_api import sync_playwright

# --- CONFIGURACIÓN ---
URL_LOGIN = "https://eventossistema.com.mx/login.html"
URL_EVENTS = "https://eventossistema.com.mx/confirmaciones/default.html"
CHECK_INTERVAL = 90 
NO_EVENTS_TEXT = "No hay eventos disponibles por el momento."
TZ = pytz.timezone("America/Mexico_City")

# Variables de entorno
USER = os.getenv("WEB_USER")
PASS = os.getenv("WEB_PASS")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Filtros Madian
LUGARES_OK = ["PALACIO DE LOS DEPORTES", "ESTADIO GNP", "AUTODROMO HERMANOS RODRIGUEZ", "ESTADIO ALFREDO HARP HELU", "DIABLOS"]
PUESTOS_NO = ["ACREDITACIONES", "ANFITRION", "MKT", "OVG", "FAN ID"]

app = Flask(__name__)

# RUTA PRINCIPAL (Esto es lo que evita el 404)
@app.route("/")
def home():
    return f"Bot Madian Online - {datetime.now(TZ).strftime('%H:%M:%S')}"

def send(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID: return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                      data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def analizar_madian(info):
    # (Toda tu lógica de 1.5 turnos y 72h que ya definimos)
    titulo = info['titulo'].upper()
    lugar = info['lugar'].upper()
    turnos = float(info['turnos'])
    is_bloque = info['is_bloque']
    try:
        inicio_dt = TZ.localize(datetime.strptime(info['inicio'], "%d/%m/%Y %H:%M"))
    except: return False, "Error fecha"
    
    ahora = datetime.now(TZ)
    if is_bloque: return False, "Es BLOQUE"
    if not any(l in lugar for l in LUGARES_OK): return False, "Lugar no permitido"
    if "TRASLADO" in titulo or "GIRA" in titulo: return False, "Gira/Traslado"
    if turnos > 1.5: return False, "Excede 1.5 turnos"
    if ahora > (inicio_dt - timedelta(hours=84)): return False, "Riesgo < 72h"
    if inicio_dt.weekday() == 6 and inicio_dt.hour < 9: return False, "Domingo mañana"
    if inicio_dt.hour >= 17: return False, "Nocturno"
    return True, "Filtros OK"

def bot_worker():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(user_agent="Mozilla/5.0...")
        page = context.new_page()
        logged = False
        while True:
            try:
                if not logged:
                    page.goto(URL_LOGIN)
                    page.wait_for_timeout(3000)
                    page.keyboard.press("Tab"); page.keyboard.type(USER)
                    page.keyboard.press("Tab"); page.keyboard.type(PASS)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(10000)
                    logged = True
                
                page.goto(URL_EVENTS, wait_until="domcontentloaded")
                page.wait_for_timeout(5000)
                content = page.inner_text("body")
                
                if "ID USUARIO" in content.upper():
                    logged = False; continue
                
                if NO_EVENTS_TEXT not in content:
                    # Lógica de clics y filtros...
                    pass
                else:
                    print(f"[{datetime.now(TZ)}] Madian: Sin eventos.")
            except Exception as e:
                print(f"Error: {e}")
                logged = False
                time.sleep(30)
            time.sleep(CHECK_INTERVAL)

# LA SECCIÓN MÁS IMPORTANTE PARA RENDER
if __name__ == "__main__":
    # Primero el hilo
    t = threading.Thread(target=bot_worker, daemon=True)
    t.start()
    # Después el servidor
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
                
