import time, re, requests, pytz
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

# === CONFIGURACIÓN MADIAN ===
USER = "TU_USUARIO_MADIAN"
PASS = "TU_PASSWORD_MADIAN"
TOKEN = "TU_TELEGRAM_TOKEN"
CHAT_ID = "TU_CHAT_ID"

URL_LOGIN = "https://eventossistema.com.mx/login/default.html"
URL_EVENTS = "https://eventossistema.com.mx/confirmaciones/default.html"
TZ = pytz.timezone("America/Mexico_City")

# Listas de Filtros
LUGARES_OK = ["PALACIO DE LOS DEPORTES", "ESTADIO GNP", "AUTODROMO HERMANOS RODRIGUEZ", "ESTADIO ALFREDO HARP HELU", "DIABLOS"]
PUESTOS_SI = ["SEGURIDAD", "SEGURIDAD PLUS", "PLUS", "BOLETAJE", "RESGUARDO", "STAFF", "ACOMODADOR", "LOCAL CREW"]
PUESTOS_NO = ["ACREDITACIONES", "ANFITRION", "MKT", "OVG", "FAN ID", "MODULOS", "TAQUILLA", "CASHLESS", "CCTV", "ACOMODADORA"]
TOP_EVENTS = ["ACDC", "SYSTEM OF A DOWN", "BTS"]

def send(msg):
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                      data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except: print("Error enviando a Telegram")

def extraer_datos(html):
    """Analiza la estructura de la tabla desplegada"""
    d = {"lugar": "", "puesto": "", "turnos": "0", "inicio": "", "fin": ""}
    try:
        lugar = re.search(r'LUGAR</td><td.*?>(.*?)</td>', html, re.I)
        d['lugar'] = lugar.group(1).strip().upper() if lugar else ""
        
        puesto = re.search(r'PUESTO</td><td.*?>(.*?)</td>', html, re.I)
        d['puesto'] = puesto.group(1).strip().upper() if puesto else ""
        
        turnos = re.search(r'TURNOS:?\s*([\d.]+)', html, re.I)
        d['turnos'] = turnos.group(1).strip() if turnos else "0"
        
        horario = re.search(r'(\d{2}/\d{2}/\d{4} \d{2}:\d{2}) AL (\d{2}/\d{2}/\d{4} \d{2}:\d{2})', html)
        if horario:
            d['inicio'], d['fin'] = horario.group(1), horario.group(2)
    except Exception as e: print(f"Error parseo: {e}")
    return d

def analizar_madian(d, titulo, es_bloque):
    ahora = datetime.now(TZ)
    titulo_u = titulo.upper()
    todo_texto = (titulo_u + " " + d['puesto']).upper()

    # 1. TRASLADO / GIRA / BLOQUE
    if any(x in titulo_u for x in ["TRASLADO", "GIRA"]) or es_bloque:
        return False, "⚠️ Traslado/Gira/Bloque (Manual)"

    # 2. EVENTOS TOP (Ignora otros filtros)
    if any(top in titulo_u for top in TOP_EVENTS):
        return True, "🔥 EVENTO TOP MADIAN 🔥"

    # 3. FILTRO DE LUGAR (Prioridad 1)
    if not any(l in d['lugar'] for l in LUGARES_OK):
        return False, f"📍 Lugar no permitido: {d['lugar']}"

    # 4. FILTRO DE PUESTOS
    if any(p in todo_texto for p in PUESTOS_NO):
        return False, f"🚫 Puesto prohibido: {todo_texto}"
    
    # 5. REGLA 84 HORAS (72h + 12h)
    try:
        inicio_dt = TZ.localize(datetime.strptime(d['inicio'], "%d/%m/%Y %H:%M"))
        if ahora > (inicio_dt - timedelta(hours=84)):
            return False, "⏳ Plazo menor a 84h"
    except: return False, "❌ Error en fecha"

    # 6. REGLA DOMINGO
    if inicio_dt.weekday() == 6: # Domingo
        if inicio_dt.hour < 9 or (inicio_dt.hour == 9 and inicio_dt.minute < 30):
            return False, "😴 Domingo antes de las 9:30 AM"

    # 7. REGLA NOCTURNA
    if inicio_dt.hour >= 17:
        return False, "🌙 Entrada Nocturna (>17:00)"

    # 8. TURNOS
    if float(d['turnos']) > 1.5:
        return False, f"⚖️ Excede 1.5 turnos ({d['turnos']})"

    return True, "✅ Apto para confirmar"

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        # LOGIN
        page.goto(URL_LOGIN)
        page.fill('input[name="usuario"]', USER)
        page.fill('input[name="password"]', PASS)
        page.click('button[type="submit"]')
        page.wait_for_timeout(5000)

        while True:
            try:
                page.goto(URL_EVENTS, wait_until="networkidle")
                div_disponibles = page.query_selector("#div_eventos_disponibles")
                
                if div_disponibles and "No hay eventos" not in div_disponibles.inner_text():
                    cards = div_disponibles.query_selector_all(".card")
                    for card in cards:
                        link = card.query_selector("h6 a")
                        if not link: continue
                        
                        titulo = link.inner_text().strip()
                        link.click() # ABRIR ESTRUCTURA
                        page.wait_for_timeout(1500)
                        
                        info = extraer_datos(card.inner_html())
                        es_bloque = "BLOQUE" in card.inner_text().upper()
                        
                        apto, motivo = analizar_madian(info, titulo, es_bloque)
                        btn_confirmar = card.query_selector("button:has-text('CONFIRMAR')")

                        if apto and btn_confirmar:
                            btn_confirmar.click()
                            page.wait_for_timeout(2000)
                            if "EVENTO LLENO" in page.content().upper():
                                send(f"❌ *LLENO:* {titulo}\nNo se pudo confirmar.")
                            else:
                                send(f"✅ *CONFIRMADO:* {titulo}\n📍 {info['lugar']}\n⏳ {info['turnos']} turnos")
                        else:
                            send(f"📋 *NUEVOS DATOS:* {titulo}\n❌ *ESTADO:* {motivo}\n📍 Lugar: {info['lugar']}\n⏳ Turnos: {info['turnos']}")

                time.sleep(90)
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(10)

if __name__ == "__main__":
    run()
