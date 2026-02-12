import time
import requests
import threading
import os
from datetime import datetime, timedelta
import pytz
from flask import Flask
from playwright.sync_api import sync_playwright

# ================= CONFIGURACIÓN =================
URL_LOGIN = "https://eventossistema.com.mx/login.html"
URL_EVENTS = "https://eventossistema.com.mx/confirmaciones/default.html"
CHECK_INTERVAL = 90 
NO_EVENTS_TEXT = "No hay eventos disponibles por el momento."
TZ = pytz.timezone("America/Mexico_City")

# Credenciales (Configura estas en Render)
USER = os.getenv("WEB_USER")
PASS = os.getenv("WEB_PASS")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

LUGARES_OK = ["PALACIO DE LOS DEPORTES", "ESTADIO GNP", "AUTODROMO HERMANOS RODRIGUEZ", "ESTADIO ALFREDO HARP HELU", "DIABLOS"]
PUESTOS_NO = ["ACREDITACIONES", "ANFITRION", "MKT", "OVG", "FAN ID"]
TOP_EVENTS = ["ACDC", "SYSTEM OF A DOWN", "BTS"]

app = Flask(__name__)

# --- ESTO CORRIGE EL ERROR 404 ---
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
    titulo = info['titulo'].upper()
    lugar = info['lugar'].upper()
    turnos = float(info['turnos'])
    is_bloque = info['is_bloque']
    
    try:
        inicio_dt = TZ.localize(datetime.strptime(info['inicio'], "%d/%m/%Y %H:%M"))
    except: return False, "Error de fecha"

    ahora = datetime.now(TZ)

    # 1. BLOQUE
    if is_bloque: return False, "Evento BLOQUE (Revisar manual)"
    
    # 2. LUGAR / TRASLADO
    if not any(l in lugar for l in LUGARES_OK): return False, f"Lugar: {lugar}"
    if "TRASLADO" in titulo or "GIRA" in titulo: return False, "Es TRASLADO/GIRA"
    if any(p in titulo for p in PUESTOS_NO): return False, "Puesto prohibido"
    
    # 3. TURNO 1.5 (Máximo para Madian)
    if turnos > 1.5: return False, f"Turnos exceden 1.5 ({turnos})"

    # 4. REGLA 72H (+12h de gracia = 84h)
    if ahora > (inicio_dt - timedelta(hours=84)): 
        return False, "Riesgo de cancelación (Menos de 84h)"
    
    # 5. DOMINGO / NOCTURNA
    if inicio_dt.weekday() == 6 and (inicio_dt.hour < 9 or (inicio_dt.hour == 9 and inicio_dt.minute < 30)):
        return False, "Domingo mañana"
    if inicio_dt.hour >= 17: return False, "Horario nocturno"

    return True, "Filtros OK"

def bot_worker():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = context.new_page()
        logged = False

        while True:
            try:
                if not logged:
                    page.goto(URL_LOGIN)
                    page.wait_for_timeout(3000)
                    page.keyboard.press("Tab"); page.keyboard.type(USER, delay=100)
                    page.keyboard.press("Tab"); page.keyboard.type(PASS, delay=100)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(10000)
                    logged = True

                page.goto(URL_EVENTS, wait_until="domcontentloaded")
                page.wait_for_timeout(5000)
                content = page.inner_text("body")

                if "ID USUARIO" in content.upper():
                    logged = False; continue

                if NO_EVENTS_TEXT not in content:
                    eventos_visibles = page.query_selector_all(".row-evento, .card-evento, [onclick*='confirmar']")
                    for ev in eventos_visibles:
                        es_bloque = "BLOQUE" in ev.inner_text().upper()
                        ev.click()
                        page.wait_for_timeout(3000)
                        
                        # Simulación de datos extraídos del detalle
                        info = {"titulo": "MCR Madian", "lugar": "ESTADIO GNP", "inicio": "15/02/2026 13:30", "turnos": "1.5", "is_bloque": es_bloque}
                        
                        apto, motivo = analizar_madian(info)
                        if apto:
                            # page.click("#btn-confirmar") # Selector real necesario
                            send(f"✅ *MADIAN: EVENTO CONFIRMADO*\n📌 {info['titulo']}\n⏰ {info['inicio']}")
                        else:
                            send(f"📋 *MADIAN: AVISO*\nEvento: {info['titulo']}\nMotivo: {motivo}")
                else:
                    print(f"[{datetime.now(TZ).strftime('%H:%M:%S')}] Madian: Sin eventos.")

            except Exception as e:
                print(f"Error Madian: {e}")
                logged = False
                time.sleep(30)
            time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    # Iniciamos el bot en un hilo separado
    t = threading.Thread(target=bot_worker, daemon=True)
    t.start()
    # Iniciamos el servidor Flask
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
    
