import time
import requests
import threading
import os
from datetime import datetime
import pytz

from flask import Flask
from playwright.sync_api import sync_playwright

# ================= CONFIGURACIÓN =================
URL_LOGIN = "https://eventossistema.com.mx/login.html"
URL_EVENTS = "https://eventossistema.com.mx/confirmaciones/default.html"

CHECK_INTERVAL = 90  # 1 minuto con 30 segundos
NO_EVENTS_TEXT = "No hay eventos disponibles por el momento."
TZ = pytz.timezone("America/Mexico_City")

# Credenciales desde Render
USER_1 = os.getenv("WEB_USER")
PASS_1 = os.getenv("WEB_PASS")
USER_2 = os.getenv("WEB_USER_2")
PASS_2 = os.getenv("WEB_PASS_2")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

app = Flask(__name__)

# ================= FUNCIONES DE APOYO =================
def send(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        # Usamos Markdown para que el diagnóstico se vea como código fuente
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def clean_event_text(text, user_label):
    """Extrae eventos disponibles o devuelve un diagnóstico si no hay claridad."""
    original_text = text
    resultado = ""
    
    # Intentamos extraer lo que está entre DISPONIBLES y CONFIRMADOS
    if "EVENTOS DISPONIBLES" in text:
        parte_despues_disp = text.split("EVENTOS DISPONIBLES")[-1]
        if "EVENTOS CONFIRMADOS" in parte_despues_disp:
            resultado = parte_despues_disp.split("EVENTOS CONFIRMADOS")[0]
        else:
            resultado = parte_despues_disp
    
    # LÓGICA DE DIAGNÓSTICO:
    # Si el texto extraído es muy corto, enviamos lo que el bot está leyendo realmente.
    if len(resultado.strip()) < 15:
        # Limpiamos saltos de línea excesivos para el reporte
        resumen = " ".join(original_text.split())[:300]
        return (f"❓ *{user_label}: Cambio detectado pero sin eventos claros.*\n\n"
                f"El bot leyó esto:\n`{resumen}...` \n\n"
                f"🕒 _Revisión: {datetime.now(TZ).strftime('%H:%M:%S')}_")

    hora_actual = datetime.now(TZ).strftime("%H:%M:%S")
    return f"*🚨 EVENTOS PARA: {user_label} 🚨*\n\n{resultado.strip()}\n\n🕒 _Actualizado: {hora_actual}_"

# ================= MOTOR DE MONITOREO =================
def monitor_account(username, password, label):
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-setuid-sandbox"]
        )
        
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        page.set_default_timeout(60000)
        logged = False

        while True:
            try:
                # Horario de operación (6 AM a 11:59 PM)
                now = datetime.now(TZ)
                if not (6 <= now.hour < 24):
                    time.sleep(60)
                    continue

                if not logged:
                    page.goto(URL_LOGIN, wait_until="networkidle")
                    page.wait_for_timeout(3000)
                    
                    # Simulación de escritura humana
                    page.keyboard.press("Tab")
                    page.keyboard.type(username, delay=120)
                    page.keyboard.press("Tab")
                    page.keyboard.type(password, delay=120)
                    page.keyboard.press("Enter")
                    
                    # Espera a que cargue la página interna
                    page.wait_for_timeout(10000)
                    logged = True

                # --- ACCIÓN DE MONITOREO ---
                page.goto(URL_EVENTS, wait_until="domcontentloaded")
                page.wait_for_timeout(5000)
                content = page.inner_text("body")

                # Verificar si la sesión expiró
                if "ID USUARIO" in content.upper() or "INGRESE" in content.upper():
                    logged = False
                    continue

                # Lógica de aviso
                if NO_EVENTS_TEXT not in content and len(content.strip()) > 50:
                    mensaje = clean_event_text(content, label)
                    send(mensaje)
                else:
                    # Log interno para Render
                    print(f"[{datetime.now(TZ).strftime('%H:%M:%S')}] {label}: Sin eventos nuevos.")

            except Exception as e:
                print(f"Error en {label}: {e}")
                logged = False
                time.sleep(30)

            time.sleep(CHECK_INTERVAL)

# ================= SERVIDOR FLASK =================
@app.route("/")
def home():
    return f"Bot Dual Activo - RAM: ~400MB - {datetime.now(TZ).strftime('%H:%M:%S')}"

if __name__ == "__main__":
    # Hilo para MADIAN (Variables: WEB_USER / WEB_PASS)
    if USER_1 and PASS_1:
        threading.Thread(target=monitor_account, args=(USER_1, PASS_1, "MADIAN"), daemon=True).start()
    
    # Hilo para SAYURI (Variables: WEB_USER_2 / WEB_PASS_2)
    if USER_2 and PASS_2:
        threading.Thread(target=monitor_account, args=(USER_2, PASS_2, "SAYURI"), daemon=True).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, use_reloader=False)
    
