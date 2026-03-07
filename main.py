import time, requests, threading, os, pytz
from datetime import datetime
from flask import Flask
from playwright.sync_api import sync_playwright

# ================= CONFIG =================
URL_LOGIN = "https://eventossistema.com.mx/login/default.html"
URL_EVENTS = "https://eventossistema.com.mx/confirmaciones/default.html"
CHECK_INTERVAL = 90 
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

def send(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID: return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                      data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def monitor_account(username, password, label):
    while True: # Bucle infinito para reiniciar el navegador si hay error crítico
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
                # Aumentamos el timeout global a 60 segundos por si la página está lenta
                context = browser.new_context(user_agent="Mozilla/5.0...", viewport={'width': 1280, 'height': 720})
                context.set_default_timeout(60000) 
                page = context.new_page()
                
                print(f"[{datetime.now(TZ)}] {label}: Iniciando Navegador.")
                
                # LOGIN CON REINTENTO
                page.goto(URL_LOGIN, wait_until="networkidle")
                page.wait_for_selector('input[name="usuario"]', state="visible")
                page.fill('input[name="usuario"]', username)
                page.fill('input[name="password"]', password)
                page.click('button[type="submit"]')
                page.wait_for_timeout(5000)

                while True:
                    try:
                        # IR A EVENTOS
                        page.goto(URL_EVENTS, wait_until="domcontentloaded")
                        # Esperamos a que el contenedor principal aparezca
                        page.wait_for_selector("#div_eventos_disponibles", timeout=45000)
                        
                        content = page.inner_text("body")

                        if "INGRESE SU" in content.upper() or "LOGIN" in content.upper():
                            print(f"[{datetime.now(TZ)}] {label}: Sesión expirada.")
                            break # Sale al bucle superior para re-loguear

                        if NO_EVENTS_TEXT not in content and len(content.strip()) > 100:
                            send(f"🚨 *EVENTO DETECTADO: {label}* 🚨\nRevisa la página de inmediato.")
                            print(f"[{datetime.now(TZ)}] {label}: ¡Evento hallado!")
                        else:
                            print(f"[{datetime.now(TZ)}] {label}: Sin novedades.")

                    except Exception as e:
                        print(f"[{datetime.now(TZ)}] {label}: Error en ciclo: {e}")
                        # Si hay timeout aquí, intentamos refrescar la página una vez
                        page.reload()
                        time.sleep(10)

                    time.sleep(CHECK_INTERVAL)
                
                browser.close() # Limpieza de memoria
        except Exception as e:
            print(f"[{datetime.now(TZ)}] {label}: Error Crítico (Reiniciando navegador): {e}")
            time.sleep(30)

@app.route("/")
def home():
    return "Bot Online 24/7"

if __name__ == "__main__":
    if USER_1: threading.Thread(target=monitor_account, args=(USER_1, PASS_1, "Madian"), daemon=True).start()
    if USER_2: threading.Thread(target=monitor_account, args=(USER_2, PASS_2, "Jimena"), daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
    
