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
TZ = pytz.timezone("America/Mexico_City")

USER = os.getenv("WEB_USER")
PASS = os.getenv("WEB_PASS")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

LUGARES_OK = ["PALACIO DE LOS DEPORTES", "ESTADIO GNP", "AUTODROMO HERMANOS RODRIGUEZ", "ESTADIO ALFREDO HARP HELU", "DIABLOS"]
PUESTOS_NO = ["ACREDITACIONES", "ANFITRION", "MKT", "OVG", "FAN ID"]
TOP_EVENTS = ["ACDC", "SYSTEM OF A DOWN", "BTS"]

app = Flask(__name__)

def send(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID: return
    try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                       data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def analizar_madian(info):
    titulo = info['titulo'].upper()
    lugar = info['lugar'].upper()
    turnos = float(info['turnos'])
    is_bloque = info['is_bloque']
    
    try:
        inicio_dt = TZ.localize(datetime.strptime(info['inicio'], "%d/%m/%Y %H:%M"))
    except: return False, "Error fecha"

    ahora = datetime.now(TZ)

    # REGLAS MADIAN
    if is_bloque: return False, "Evento tipo BLOQUE (Requiere revisión manual)"
    if not any(l in lugar for l in LUGARES_OK): return False, f"Lugar: {lugar}"
    if "TRASLADO" in titulo or "GIRA" in titulo: return False, "Es TRASLADO/GIRA"
    if any(p in titulo for p in PUESTOS_NO): return False, "Puesto prohibido"
    
    # Límite 1.5 turnos para Madian
    if turnos > 1.5: return False, f"Turnos exceden 1.5 ({turnos})"

    # Regla 72h + 12h gracia
    if ahora > (inicio_dt - timedelta(hours=84)): return False, "Riesgo cancelación (<84h)"
    
    # Domingo y Nocturnas
    if inicio_dt.weekday() == 6 and (inicio_dt.hour < 9 or (inicio_dt.hour == 9 and inicio_dt.minute < 30)):
        return False, "Domingo antes 9:30 AM"
    if inicio_dt.hour >= 17: return False, "Horario nocturno"

    if any(top in titulo for top in TOP_EVENTS): return True, "🔥 EVENTO TOP MADIAN 🔥"
    return True, "Filtros OK"

def bot_worker():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(user_agent="Mozilla/5.0...")
        page = context.new_page()
        while True:
            try:
                page.goto(URL_LOGIN)
                page.keyboard.press("Tab"); page.keyboard.type(USER)
                page.keyboard.press("Tab"); page.keyboard.type(PASS)
                page.keyboard.press("Enter"); page.wait_for_timeout(8000)
                page.goto(URL_EVENTS)
                
                # Detectar BLOQUE antes de abrir
                # (Asumiendo que el icono tiene clase 'label-bloque' o texto 'BLOQUE')
                eventos_elementos = page.query_selector_all(".row-evento") 
                for el in eventos_elementos:
                    es_bloque = "BLOQUE" in el.inner_text().upper()
                    el.click(); page.wait_for_timeout(2000)
                    
                    # Simulación de lectura de datos del modal
                    datos = {"titulo": "MCR", "lugar": "ESTADIO GNP", "turnos": "1.5", "inicio": "14/02/2026 13:30", "is_bloque": es_bloque}
                    
                    apto, motivo = analizar_madian(datos)
                    if apto:
                        page.click("#confirmar") # Selector real necesario
                        send(f"✅ MADIAN: CONFIRMADO {datos['titulo']}")
                    else:
                        send(f"📋 MADIAN: {datos['titulo']} - {motivo}")
            except: pass
            time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    threading.Thread(target=bot_worker, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
    
