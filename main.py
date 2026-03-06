import time
import requests
import threading
import os
from datetime import datetime
import pytz

from flask import Flask
from playwright.sync_api import sync_playwright

# ================= CONFIG =================
# Verifica si es login.html o login/default.html según tu plataforma
URL_LOGIN = "https://eventossistema.com.mx/login/default.html"
URL_EVENTS = "https://eventossistema.com.mx/confirmaciones/default.html"

CHECK_INTERVAL = 90  # Notificación cada 1:30 minutos exactos
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
        # Enviamos sin esperar respuesta larga para no retrasar el bot
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=5)
    except Exception as e:
        print(f"Error enviando Telegram: {e}")

def clean_event_text(text, user_label):
    resultado = text
    # Cortamos información irrelevante de la página para que el mensaje no sea gigante
    if "EVENTOS CONFIRMADOS" in text:
        resultado = text.split("EVENTOS CONFIRMADOS")[0]
    
    if "EVENTOS DISPONIBLES" in resultado:
        parts = resultado.split("EVENTOS DISPONIBLES")
        resultado = f"*🚨 ¡HAY EVENTOS!: {user_label} 🚨*\n" + parts[-1]
    
    hora_actual = datetime.now(TZ).strftime("%H:%M:%S")
    return f"{resultado.strip()}\n\n🕒 _Revisión: {hora_actual}_"

# ================= LÓGICA DEL MONITOR =================
def monitor_account(username, password, label):
    """Monitoreo continuo 24/7 con aviso insistente cada 90s"""
    with sync_playwright() as p:
        # Argumentos para evitar errores en servidores como Render
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        logged = False

        print(f"[{datetime.now(TZ)}] {label}: Bot iniciado.")

        while True:
            try:
                if not logged:
                    print(f"[{datetime.now(TZ)}] {label}: Intentando Login...")
                    page.goto(URL_LOGIN, wait_until="networkidle")
                    page.wait_for_timeout(3000)
                    
                    # Proceso de Login manual simulado
                    page.focus('input[name="usuario"]') # Ajusta si el selector cambia
                    page.keyboard.type(username, delay=100)
                    page.keyboard.press("Tab")
                    page.keyboard.type(password, delay=100)
                    page.keyboard.press("Enter")
                    
                    page.wait_for_timeout(8000) # Tiempo para carga tras login
                    logged = True

                # --- REVISIÓN DE EVENTOS ---
                page.goto(URL_EVENTS, wait_until="domcontentloaded")
                page.wait_for_timeout(4000) # Espera a que el div de eventos cargue
                
                content = page.inner_text("body")

                # Verificación de Sesión Activa
                if "INGRESE SU" in content.upper() or "LOGIN" in content.upper():
                    print(f"[{datetime.now(TZ)}] {label}: Sesión perdida, re-logueando...")
                    logged = False
                    continue

                # Lógica de Notificación
                if NO_EVENTS_TEXT not in content and len(content.strip()) > 100:
                    mensaje = clean_event_text(content, label)
                    send(mensaje)
                    print(f"[{datetime.now(TZ)}] {label}: ¡Evento detectado! Notificación enviada.")
                else:
                    print(f"[{datetime.now(TZ)}] {label}: Todo tranquilo (Sin eventos).")

            except Exception as e:
                print(f"Error crítico en {label}: {e}")
                logged = False # Forzamos re-login por si el error fue por desconexión
                time.sleep(20) 

            # Espera exacta de 90 segundos antes de la siguiente vuelta
            time.sleep(CHECK_INTERVAL)

# ================= SERVIDOR Y LANZAMIENTO =================
@app.route("/")
def home():
    return f"Bot Dual Notificador - Estado: ACTIVO - {datetime.now(TZ).strftime('%H:%M:%S')}"

if __name__ == "__main__":
    # Iniciar Cuenta 1
    if USER_1 and PASS_1:
        threading.Thread(target=monitor_account, args=(USER_1, PASS_1, "CUENTA 1"), daemon=True).start()
    else:
        print("Faltan credenciales de CUENTA 1")
    
    # Iniciar Cuenta 2
    if USER_2 and PASS_2:
        threading.Thread(target=monitor_account, args=(USER_2, PASS_2, "CUENTA 2"), daemon=True).start()
    else:
        print("Faltan credenciales de CUENTA 2")

    # Puerto para Render
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, use_reloader=False)
    
