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

CHECK_INTERVAL = 90  # 1:30 minutos
NO_EVENTS_TEXT = "No hay eventos disponibles por el momento."
TZ = pytz.timezone("America/Mexico_City")

# Variables de entorno
USER_1 = os.getenv("WEB_USER")
PASS_1 = os.getenv("WEB_PASS")
USER_2 = os.getenv("WEB_USER_2")
PASS_2 = os.getenv("WEB_PASS_2")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

app = Flask(__name__)

# ================= FUNCIONES AUXILIARES =================
def send(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def clean_event_text(text, user_label):
    resultado = text
    if "EVENTOS CONFIRMADOS" in text:
        resultado = text.split("EVENTOS CONFIRMADOS")[0]
    
    if "EVENTOS DISPONIBLES" in resultado:
        parts = resultado.split("EVENTOS DISPONIBLES")
        resultado = f"*🚨 EVENTOS PARA: {user_label} 🚨*\n" + parts[-1]
    
    hora_actual = datetime.now(TZ).strftime("%H:%M:%S")
    return f"{resultado.strip()}\n\n🕒 _Actualizado: {hora_actual}_"

# ================= LÓGICA DEL MONITOR =================
def monitor_account(username, password, label):
    """Monitoreo continuo 24/7"""
    with sync_playwright() as p:
        # Lanzamos el navegador con argumentos para estabilidad
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        logged = False

        while True:
            try:
                if not logged:
                    print(f"[{datetime.now(TZ)}] {label}: Iniciando sesión...")
                    page.goto(URL_LOGIN, wait_until="networkidle")
                    page.wait_for_timeout(3000)
                    
                    # Proceso de Login
                    page.keyboard.press("Tab")
                    page.keyboard.type(username, delay=100)
                    page.keyboard.press("Tab")
                    page.keyboard.type(password, delay=100)
                    page.keyboard.press("Enter")
                    
                    page.wait_for_timeout(10000)
                    logged = True

                # --- MONITOREO ---
                page.goto(URL_EVENTS, wait_until="domcontentloaded")
                page.wait_for_timeout(5000)
                content = page.inner_text("body")

                # Detectar si sacó de la sesión (ej. timeout del servidor)
                if "ID USUARIO" in content.upper() or "INGRESE" in content.upper():
                    print(f"[{datetime.now(TZ)}] {label}: Sesión expirada, re-logueando...")
                    logged = False
                    continue

                # Analizar eventos
                if NO_EVENTS_TEXT not in content and len(content.strip()) > 50:
                    mensaje = clean_event_text(content, label)
                    send(mensaje)
                    # SE ELIMINÓ EL SLEEP DE 300 PARA NOTIFICAR CADA 90 SEGUNDOS
                else:
                    print(f"[{datetime.now(TZ)}] {label}: Sin novedades.")

            except Exception as e:
                print(f"Error en {label}: {e}")
                logged = False
                time.sleep(30) # Espera antes de reintentar tras un error

            time.sleep(CHECK_INTERVAL)

# ================= FLASK Y HILOS =================
@app.route("/")
def home():
    return f"Bot Dual Online - {datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')}"

if __name__ == "__main__":
    if USER_1 and PASS_1:
        threading.Thread(target=monitor_account, args=(USER_1, PASS_1, "CUENTA 1"), daemon=True).start()
    
    if USER_2 and PASS_2:
        threading.Thread(target=monitor_account, args=(USER_2, PASS_2, "CUENTA 2"), daemon=True).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, use_reloader=False)
    
