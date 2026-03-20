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

# ================= LÓGICA DEL MONITOR (NUEVA ESTRUCTURA ANTI-CRASH) =================
def run_once(username, password, label):
    """Realiza un solo escaneo y cierra TODO para liberar RAM"""
    try:
        with sync_playwright() as p:
            # Lanzamos navegador con flags de ahorro de memoria extrema
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox", 
                    "--disable-dev-shm-usage", 
                    "--disable-gpu",
                    "--single-process" # Ayuda en entornos de poca RAM como Render
                ]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            # 1. Login
            page.goto(URL_LOGIN, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(2000)
            page.keyboard.press("Tab")
            page.keyboard.type(username, delay=50)
            page.keyboard.press("Tab")
            page.keyboard.type(password, delay=50)
            page.keyboard.press("Enter")
            
            # Esperar a que cargue el dashboard tras login
            page.wait_for_timeout(8000)

            # 2. Ir a Eventos
            page.goto(URL_EVENTS, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(4000)
            
            content = page.inner_text("body")

            # 3. Analizar
            if NO_EVENTS_TEXT not in content and len(content.strip()) > 50:
                # Verificar que no estemos en la pantalla de login de nuevo
                if "ID USUARIO" not in content.upper():
                    mensaje = clean_event_text(content, label)
                    send(mensaje)
                else:
                    print(f"[{datetime.now(TZ)}] {label}: Error de sesión en este ciclo.")
            else:
                print(f"[{datetime.now(TZ)}] {label}: Sin novedades.")

            # 4. Cierre total
            browser.close()
            
    except Exception as e:
        print(f"[{datetime.now(TZ)}] Error crítico en ciclo de {label}: {e}")
        # No enviamos mensaje a Telegram por cada crash para evitar spam, 
        # el bucle simplemente reintentará en 90s.

def monitor_account(username, password, label):
    """Bucle infinito que llama a la función de escaneo limpio"""
    while True:
        run_once(username, password, label)
        time.sleep(CHECK_INTERVAL)

# ================= FLASK Y HILOS =================
@app.route("/")
def home():
    return f"Bot Dual Online (Anti-Crash) - {datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')}"

if __name__ == "__main__":
    # Si usas cuentas separadas en Renders distintos, solo se activará el que tenga sus credenciales
    if USER_1 and PASS_1:
        threading.Thread(target=monitor_account, args=(USER_1, PASS_1, "MADIAN"), daemon=True).start()
    
    if USER_2 and PASS_2:
        threading.Thread(target=monitor_account, args=(USER_2, PASS_2, "JIMENA"), daemon=True).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, use_reloader=False)
    
