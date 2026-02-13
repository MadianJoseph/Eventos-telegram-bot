import time, re, requests, pytz, os, threading
from datetime import datetime, timedelta
from flask import Flask
from playwright.sync_api import sync_playwright

# --- SERVIDOR PARA RENDER (EVITA ERROR DE PUERTOS) ---
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot de Madian en ejecución...", 200

# --- CONFIGURACIÓN DESDE VARIABLES DE ENTORNO ---
USER = os.getenv("WEB_USER")
PASS = os.getenv("WEB_PASS")
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

URL_LOGIN = "https://eventossistema.com.mx/login/default.html"
URL_EVENTS = "https://eventossistema.com.mx/confirmaciones/default.html"
TZ = pytz.timezone("America/Mexico_City")

# Filtros Listas
LUGARES_OK = ["PALACIO DE LOS DEPORTES", "ESTADIO GNP", "AUTODROMO HERMANOS RODRIGUEZ", "ESTADIO ALFREDO HARP HELU", "DIABLOS"]
PUESTOS_NO = ["ACREDITACIONES", "ANFITRION", "MKT", "OVG", "FAN ID", "MODULOS", "TAQUILLA", "CASHLESS", "CCTV", "ACOMODADORA"]
TOP_EVENTS = ["ACDC", "SYSTEM OF A DOWN", "BTS"]

def send(msg):
    if not TOKEN or not CHAT_ID: return
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                      data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def extraer_datos_tabla(card_element):
    """Extrae datos de la tabla interna una vez desplegada"""
    d = {"lugar": "", "puesto": "", "turnos": "0", "inicio": "", "fin": ""}
    try:
        html = card_element.inner_html()
        # Buscar Puesto
        puesto_match = re.search(r'PUESTO</td><td.*?>(.*?)</td>', html, re.I)
        d['puesto'] = puesto_match.group(1).strip().upper() if puesto_match else ""
        
        # Buscar Lugar
        lugar_match = re.search(r'LUGAR</td><td.*?>(.*?)</td>', html, re.I)
        d['lugar'] = lugar_match.group(1).strip().upper() if lugar_match else ""
        
        # Buscar Horario y Turnos (Estructura: 15/02/2026 08:30 AL 15/02/2026 20:30, TURNOS: 1.5)
        horario_completo = re.search(r'(\d{2}/\d{2}/\d{4} \d{2}:\d{2}) AL (\d{2}/\d{2}/\d{4} \d{2}:\d{2}), TURNOS:\s*([\d.]+)', html)
        if horario_completo:
            d['inicio'] = horario_completo.group(1)
            d['fin'] = horario_completo.group(2)
            d['turnos'] = horario_completo.group(3)
    except Exception as e:
        print(f"Error extrayendo tabla: {e}")
    return d

def analizar_madian(d, titulo, es_bloque):
    ahora = datetime.now(TZ)
    titulo_u = titulo.upper()
    todo_texto = (titulo_u + " " + d['puesto']).upper()

    if any(x in titulo_u for x in ["TRASLADO", "GIRA"]) or es_bloque:
        return False, "⚠️ TRASLADO/GIRA/BLOQUE"

    if any(top in titulo_u for top in TOP_EVENTS):
        return True, "🔥 EVENTO TOP 🔥"

    if not any(l in d['lugar'] for l in LUGARES_OK):
        return False, f"📍 Lugar: {d['lugar']}"

    if any(p in todo_texto for p in PUESTOS_NO):
        return False, "🚫 Puesto prohibido"
    
    try:
        inicio_dt = TZ.localize(datetime.strptime(d['inicio'], "%d/%m/%Y %H:%M"))
        # Regla 84 horas (72h + 12h gracia)
        if ahora > (inicio_dt - timedelta(hours=84)):
            return False, "⏳ Menos de 84h"
    except: return False, "❌ Error en fecha"

    # Reglas Madian: Domingo y Noche
    if inicio_dt.weekday() == 6: 
        if inicio_dt.hour < 9 or (inicio_dt.hour == 9 and inicio_dt.minute < 30):
            return False, "😴 Domingo temprano"

    if inicio_dt.hour >= 17:
        return False, "🌙 Nocturno (Entrada >= 17:00)"

    if float(d['turnos']) > 1.5:
        return False, f"⚖️ Turnos: {d['turnos']}"

    return True, "✅ Filtros cumplidos"

def bot_worker():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context()
        page = context.new_page()
        
        try:
            page.goto(URL_LOGIN)
            page.fill('input[name="usuario"]', USER)
            page.fill('input[name="password"]', PASS)
            page.click('button[type="submit"]')
            page.wait_for_timeout(5000)

            while True:
                page.goto(URL_EVENTS, wait_until="networkidle")
                # FOCO SOLO EN DISPONIBLES
                container = page.query_selector("#div_eventos_disponibles")
                
                if container and "No hay eventos" not in container.inner_text():
                    cards = container.query_selector_all(".card.mb-2")
                    for card in cards:
                        link = card.query_selector("a[data-bs-toggle='collapse']")
                        if not link: continue
                        
                        titulo = link.inner_text().split('\n')[0].strip()
                        # Si está colapsado, dar clic para ver detalles
                        if "collapsed" in link.get_attribute("class"):
                            link.click()
                            page.wait_for_timeout(1000)
                        
                        info = extraer_datos_tabla(card)
                        es_bloque = "BLOQUE" in card.inner_text().upper()
                        
                        apto, motivo = analizar_madian(info, titulo, es_bloque)
                        btn_confirmar = card.query_selector("button:has-text('CONFIRMAR')")

                        if apto and btn_confirmar:
                            btn_confirmar.click()
                            page.wait_for_timeout(2000)
                            # Verificar si salió el modal de lleno
                            if page.locator("text=EVENTO LLENO").is_visible():
                                send(f"❌ *LLENO:* {titulo}")
                            else:
                                send(f"✅ *CONFIRMADO:* {titulo}\n📍 {info['lugar']}\n⏳ {info['turnos']} turnos")
                        else:
                            # Notificar aunque no se confirme
                            send(f"📋 *NUEVO EVENTO:* {titulo}\n❌ *ESTADO:* {motivo}\n📍 Lugar: {info['lugar']}\n⏳ Turnos: {info['turnos']}")
                
                time.sleep(90)
                page.reload()
        except Exception as e:
            print(f"Error en el bot: {e}")
            time.sleep(30)

if __name__ == "__main__":
    # Hilo para el bot
    threading.Thread(target=bot_worker, daemon=True).start()
    # Servidor Flask para Render
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
