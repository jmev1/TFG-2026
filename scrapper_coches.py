#Ha tocado migrar el scraper a camoufox por temas de bloqueo, refactorizar y ordenar todo el scrapper.
import asyncio
import random
import json
import os
import re
import time
import psycopg2
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode
from psycopg2.extras import execute_values

# Intentar importar camoufox
try:
    from camoufox.async_api import AsyncCamoufox
    CAMOUFOX_AVAILABLE = True
except ImportError:
    CAMOUFOX_AVAILABLE = False
    print("   Camoufox no instalado")
    print("   pip install camoufox --break-system-packages")
    print("   camoufox fetch")

# Directorios
DATA_DIR = "data/"
CONFIG_DIR = "config/"
URL_BASE = "https://www.coches.net/segunda-mano/"
DB_CONFIG_FILE = "config/db_config.json"

# Estadisticas de sesion
hits = 0
paginas = 1
anuncios_extendidos = 0
no_disponibles = 0
min_wait = 1000
max_wait = 3000

# Control de sesion
(1000000, 1000, 3000, 1000, 3000)
session_requests = 0
MAX_REQUESTS_PER_SESSION = 1000000
SESSION_PAUSE_MIN = 1000
SESSION_PAUSE_MAX = 3000

HEADLESS = False

# Constantes
MARCAS = ["ABARTH", "AIWAYS", "ALFA ROMEO", "ALPINE", "ARO", "ASIA", "ASIA MOTORS", "ASTON MARTIN", "AUDI", "AUSTIN", "BAIC", "BENTLEY", "BERTONE", "BESTUNE", "BMW", "BYD", "CADILLAC", "CHEVROLET", "CHRYSLER", "CITROEN", "CORVETTE", "CUPRA", "DACIA", "DAEWOO", "DAIHATSU", "DAIMLER", "DFSK", "DODGE", "DONGFENG", "DR AUTOMOBILES", "DS", "EBRO", "EVO", "FERRARI", "FIAT", "FISKER", "FORD", "HONDA", "HYUNDAI", "JAGUAR", "JEEP", "KIA", "LAMBORGHINI", "LAND-ROVER", "LEXUS", "MAZDA", "MERCEDES-BENZ", "MINI", "NISSAN", "OPEL", "PEUGEOT", "PORSCHE", "RENAULT", "SEAT", "SKODA", "TESLA", "TOYOTA", "VOLKSWAGEN", "VOLVO"]
CAMBIOS = ["Manual", "Automático"]
FUELES = ["Gasolina", "Diesel", "Híbrido", "Eléctrico", "Híbrido enchufable", "Gas licuado (GLP)", "Gas natural (CNG)"]
TIPOS = ['Berlina', 'Familiar', 'Coupe', 'Monovolumen', 'SUV', 'Cabrio', 'Pick Up']

RE_YEAR = re.compile(r"^(19\d{2}|20\d{2})$")
RE_KM = re.compile(r"^([\d.,]+)\s*km$", re.IGNORECASE)
RE_CV = re.compile(r"^(\d+)\s*cv$", re.IGNORECASE)
RE_CC = re.compile(r"^(\d+)\s*cc$", re.IGNORECASE)
RE_DOORS = re.compile(r"^(\d+)\s*puertas?$", re.IGNORECASE)
RE_SEATS = re.compile(r"^(\d+)\s*plazas?$", re.IGNORECASE)
RE_LABEL = re.compile(r"^etiqueta\s+", re.IGNORECASE)
RE_LOCATION = re.compile(r"-en-([a-zA-Z\-]+)-\d+", re.IGNORECASE)

ORGANIC_NAVIGATION = [
    "https://www.coches.net/",
    "https://www.coches.net/segunda-mano/",
    "https://www.coches.net/bmw-segunda-mano/",
    "https://www.coches.net/audi-segunda-mano/",
]


# =============================================================================
# UTILIDADES
# =============================================================================

##Extrae el ID del anuncio de la URL (número antes de -covo.aspx)
def extract_id_from_url(url):
    # https://www.coches.net/...-59641435-covo.aspx → 59641435
    match = re.search(r'-(\d+)-covo\.aspx', url)
    if match:
        return match.group(1)
    
    # Alternativa: buscar número largo al final
    match = re.search(r'-(\d{7,})-', url)
    if match:
        return match.group(1)
    
    return None


# =============================================================================
# HUMANIZACION
# =============================================================================

async def random_delay(min_ms=2000, max_ms=5000):
    if random.random() < 0.15:
        delay = random.uniform(max_ms * 3, max_ms * 6)
        print("Pausa larga (distraccion)")
    elif random.random() < 0.10:
        delay = random.uniform(min_ms * 0.5, min_ms)
    else:
        mean = (min_ms + max_ms) / 2 / 1000
        delay = random.lognormvariate(mean, 0.4) * 1000
        delay = max(min_ms, min(max_ms * 2, delay))
    await asyncio.sleep(delay / 1000)


async def delay_between_ads():
    global session_requests
    session_requests += 1
    
    if session_requests >= MAX_REQUESTS_PER_SESSION:
        print(f"Pausa de sesion ({session_requests} peticiones)")
        pause = random.uniform(SESSION_PAUSE_MIN, SESSION_PAUSE_MAX)
        print(f"Esperando {pause/1000:.0f} segundos...")
        await asyncio.sleep(pause / 1000)
        session_requests = 0
        return
    
    base_delay = random.uniform(min_wait, max_wait)
    if random.random() < 0.25:
        base_delay += random.uniform(8000, 20000)
        print("Pausa extra entre anuncios")
    if random.random() < 0.15:
        base_delay += random.uniform(30000, 60000)
        print("Pausa muy larga (distraccion)")
    await asyncio.sleep(base_delay / 1000)


async def human_scroll(page, max_rounds=30):
    print("Scroll (humanizar)")
    prev_count = 0
    
    for i in range(max_rounds):
        delta = random.uniform(500, 900) if random.random() < 0.2 else random.uniform(200, 450)
        await page.mouse.wheel(0, delta)
        await random_delay()
        
        if random.random() < 0.12:
            await page.mouse.wheel(0, -random.uniform(150, 350))
            await random_delay()
        
        if random.random() < 0.08:
            await random_delay()
        
        if random.random() < 0.25:
            await page.mouse.move(random.randint(200, 1000), random.randint(200, 600))
            await random_delay()
        
        count = await page.locator("ul.mt-CardAd-attr").count()
        if count == prev_count and i > 5:
            await page.mouse.wheel(0, random.uniform(600, 1000))
            await asyncio.sleep(2)
            if await page.locator("ul.mt-CardAd-attr").count() == count:
                print("Fin del scroll")
                break
        prev_count = count


async def human_scroll_detail_page(page):
    print("Scroll pagina detalle")
    await asyncio.sleep(random.uniform(1.5, 3.5))
    
    for _ in range(random.randint(4, 10)):
        delta = random.uniform(150, 400)
        if random.random() < 0.25:
            delta = random.uniform(450, 800)
        await page.mouse.wheel(0, delta)
        
        pause = random.uniform(1000, 2500)
        if random.random() < 0.25:
            pause = random.uniform(3000, 8000)
        await asyncio.sleep(pause / 1000)
        
        if random.random() < 0.18:
            await page.mouse.wheel(0, -random.uniform(100, 300))
            await asyncio.sleep(random.uniform(800, 2000) / 1000)
    
    if random.random() < 0.25:
        await page.mouse.wheel(0, -random.uniform(800, 1500))
        await asyncio.sleep(random.uniform(1500, 3500) / 1000)


async def simulate_page_interaction(page):
    if random.random() < 0.25:
        try:
            selector = random.choice(["img", "a", "button:not([type='submit'])"])
            locator = page.locator(selector)
            count = await locator.count()
            if count > 0:
                element = locator.nth(random.randint(0, min(count - 1, 5)))
                box = await element.bounding_box()
                if box:
                    await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                    await asyncio.sleep(random.uniform(0.3, 1.0))
        except:
            pass


# =============================================================================
# NORMALIZACION
# =============================================================================

def normalize_text(s):
    return s.replace("\xa0", " ").replace("\u202f", " ").replace("\u2009", " ").strip() if s else None

def normalize_price(texto):
    if not texto:
        return None
    limpio = texto.replace("\xa0", "").replace("\u202f", " ").replace("\u2009", " ").replace("€", "").replace(".", "").strip()
    return int(limpio) if limpio.isdigit() else None

def normalize_km(texto):
    if not texto:
        return None
    limpio = texto.replace("\xa0", "").replace("km", "").replace(",", "").replace(".", "").strip()
    try:
        return int(limpio)
    except:
        return None

def normalize_cv(texto):
    if not texto:
        return None
    limpio = texto.replace("\xa0", "").replace("\u202f", " ").replace("\u2009", " ").replace("cv", "").replace(",", "").strip()
    return int(limpio) if limpio.isdigit() else None

def normalize_cc(texto):
    if not texto:
        return None
    limpio = texto.replace("\xa0", "").replace("\u202f", " ").replace("\u2009", " ").replace("cc", "").replace(",", "").strip()
    return int(limpio) if limpio.isdigit() else None

def normalize_transmission(texto):
    if not texto:
        return None
    return texto.replace("\xa0", "").replace("\u202f", " ").replace("\u2009", " ").replace("Cambio", "").replace("<strong>", "").replace("</strong>", "").strip()

def normalize_doors(texto):
    if not texto:
        return None
    limpio = texto.replace("\xa0", "").replace("\u202f", " ").replace("\u2009", " ").replace("Puertas", "").replace("puertas", "").replace("<strong>", "").replace("</strong>", "").strip()
    try:
        return int(limpio)
    except:
        return None

def normalize_seats(texto):
    if not texto:
        return None
    limpio = texto.replace("\xa0", "").replace("\u202f", " ").replace("\u2009", " ").replace("Plazas", "").replace("plazas", "").replace("<strong>", "").replace("</strong>", "").strip()
    try:
        return int(limpio)
    except:
        return None

def obtain_brand(modelo):
    if not modelo:
        return None
    modelo = modelo.upper().strip()
    for marca in sorted(MARCAS, key=len, reverse=True):
        if modelo.startswith(marca):
            return marca
    return None


# =============================================================================
# DETECCION
# =============================================================================

async def is_ad_unavailable(page):
    try:
        for selector in ["div.sui-MoleculeNotification--system", "div.sui-MoleculeNotification-content", ".sui-MoleculeNotification"]:
            try:
                notification = page.locator(selector)
                if await notification.count() > 0:
                    text = (await notification.inner_text()).lower()
                    if "ya no está disponible" in text or "ya no esta disponible" in text or "no está disponible" in text:
                        print("Detectada notificacion de anuncio no disponible")
                        return True
            except:
                pass
        
        html = (await page.content()).lower()
        for indicator in ["el anuncio al que intentas acceder ya no está disponible", "este anuncio ya no está disponible", "anuncio no disponible", "anuncio eliminado", "anuncio vendido"]:
            if indicator in html:
                print(f"Detectado: {indicator}")
                return True
        
        return False
    except:
        return False


async def is_blocked(page):
    try:
        html = (await page.content()).lower()
        title = (await page.title()).lower()
        for indicator in ["ups! parece que algo no va bien", "algo en tu navegador nos hizo pensar", "captcha"]:
            if indicator in html or indicator in title:
                await page.screenshot(path="blocked.png") 
                return True   
        return False
    except:
        await page.screenshot(path="blocked.png")
        return False


async def extract_text(locator):
    try:
        if await locator.count() == 0:
            return None
        return (await locator.first.inner_text()).strip()
    except:
        return None


# =============================================================================
# EXTRACCION
# =============================================================================

async def obtain_info(item):
    """Extrae info basica de un anuncio en el listado"""
    try:
        car_id = await item.get_attribute("data-ad-id")
        price = normalize_price(await extract_text(item.locator('[class="mt-CardAdPrice-cashAmount"]')))
        
        title_link = item.locator("a.mt-CardAd-infoHeaderTitleLink")
        try:
            model = await title_link.inner_text()
            url = await title_link.get_attribute("href")
        except:
            return None
        
        attrs = item.locator("ul.mt-CardAd-attr li.mt-CardAd-attrItem")
        fuel = year = km = cv = location = None
        
        try: fuel = (await attrs.nth(0).inner_text()).strip()
        except: pass
        try: year = (await attrs.nth(1).inner_text()).strip()
        except: pass
        try: km = normalize_km(await attrs.nth(2).inner_text())
        except: pass
        try: cv = normalize_cv(await attrs.nth(3).inner_text())
        except: pass
        try: location = (await attrs.nth(4).inner_text()).strip()
        except: pass
        
        return {"id": car_id, "price": price, "model": model, "fuel": fuel, "year": year, "km": km, "cv": cv, "location": location, "url": url, "extendido": "N"}
    except Exception as e:
        print(f"Error extrayendo info: {e}")
        return None


async def obtain_extended_info_from_detail(page):
    """Extrae información extendida directamente de la página de detalle actual"""
    global anuncios_extendidos, no_disponibles
    
    try:
        # Obtener ID de la URL
        current_url = page.url
        car_id = extract_id_from_url(current_url)
        
        if not car_id:
            print(f"No se pudo extraer ID de: {current_url}")
            return None
        
        print(f"ID: {car_id}")
        
        # Verificar si el anuncio está disponible
        if await is_ad_unavailable(page):
            print("Anuncio NO DISPONIBLE")
            no_disponibles += 1
            return {
                "id": car_id,
                "url": current_url,
                "extendido": "NO DISPONIBLE",
                "fecha_no_disponible": time.strftime("%Y-%m-%d %H:%M:%S")
            }
        
        # Verificar bloqueo
        if await is_blocked(page):
            print("BLOQUEADO")
            save_state(page.url)
            return None
        
        # Scroll por la página
        await human_scroll_detail_page(page)
        
        # Extraer atributos
        try:
            attrs_text = await page.locator("ul.mt-PanelAdDetails-data").nth(0).inner_text()
        except:
            attrs_text = ""
        
        cc = fuel = year = km = cv = transmission = doors = seats = label = car_type = None
        
        for line in attrs_text.split("\n"):
            clean_line = line.strip()
            if not clean_line:
                continue
            
            normalized = normalize_text(clean_line)
            
            if RE_CC.match(clean_line): cc = normalize_cc(clean_line)
            if clean_line in FUELES: fuel = clean_line
            if RE_YEAR.match(clean_line): year = int(clean_line)
            if normalized and RE_KM.match(normalized): km = normalize_km(clean_line)
            if RE_CV.match(clean_line): cv = normalize_cv(clean_line)
            if normalize_transmission(clean_line) in CAMBIOS: transmission = normalize_transmission(clean_line)
            if RE_DOORS.match(clean_line): doors = normalize_doors(clean_line)
            if RE_SEATS.match(clean_line): seats = normalize_seats(clean_line)
            if RE_LABEL.match(clean_line): label = clean_line
            if clean_line in TIPOS: car_type = clean_line

        
        # Modelo
        try:
            model = await page.locator("div.mt-PanelAdInfo-title > div > h1").inner_text()
        except:
            model = None
        
        brand = obtain_brand(model)
        
        # Precio
        try:
            price = normalize_price(await page.locator("div.mt-CardAdPrice-cash p.mt-CardAdPrice-cashAmount").inner_text())
        except:
            try:
                price_text = await page.locator("span.mt-NavigationAdToolbar-price").inner_text()
                price = normalize_price(price_text)
            except:
                price = None
        
        # Comentarios
        comments = None
        try:
            comments_loc = page.locator("div.mt-PanelAdDetails-commentsContent")
            if await comments_loc.count() > 0:
                comments = await comments_loc.inner_text()
        except:
            pass
        
        # Precio original
        original_price = None
        try:
            op_loc = page.locator("p.mt-TitleBasic-desc:has-text('Precio nuevo sin extras') b")
            if await op_loc.count() > 0:
                original_price = normalize_price(await op_loc.inner_text())
        except:
            pass
        
        # Ubicación
        location = None
        try:
            location =  re.search(r"-en-([a-zA-Z\-]+)-\d+", current_url)
            location = location.group(1)
            # print(location)
        except:
            location = None
            pass
        
        extended_result = {
            "id": car_id,
            "price": price,
            "original_price": original_price,
            "model": model,
            "brand": brand,
            "fuel": fuel,
            "year": year,
            "km": km,
            "cv": cv,
            "cc": cc,
            "location": location,
            "url": current_url,
            "extendido": "S",
            "transmission": transmission,
            "doors": doors,
            "seats": seats,
            "type": car_type,
            "label": label,
            "comments": comments
        }
        
        anuncios_extendidos += 1
        #print(extended_result)
        return extended_result
        
    except Exception as e:
        print(f"Error obteniendo info extendida: {e}")
        return None


# =============================================================================
# PERSISTENCIA
# =============================================================================

def save_item(result):
    global hits
    os.makedirs(DATA_DIR, exist_ok=True)
    ruta = os.path.join(DATA_DIR, f"{result['id']}.json")
    
    if os.path.exists(ruta):
        with open(ruta, "r", encoding="utf-8") as f:
            saved = json.load(f)
        
        if (result.get("extendido") == "S" and saved.get("extendido") != "S") or \
           (result.get("extendido") == "NO DISPONIBLE" and saved.get("extendido") not in ["S", "NO DISPONIBLE"]):
            print(f"Actualizando {result['id']} -> {result.get('extendido')}")
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=4, ensure_ascii=False)
            hits += 1
        else:
            print(f"Ya existe: {result['id']}")
    else:
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=4, ensure_ascii=False)
        hits += 1
        print(f"Guardado: {result['id']}")


def load_state():
    global min_wait, max_wait
    ruta = os.path.join(CONFIG_DIR, "state.json")
    if not os.path.exists(ruta):
        return URL_BASE
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            state = json.load(f)
        marca = int(state.get('marca', 0))
        pagina = int(state.get('pagina', 1))
        # min_wait = state.get('min', 8000)
        # max_wait = state.get('max', 20000)
        print(f"Tiempos: ({min_wait}, {max_wait})")
        if marca > 0 or pagina > 1:
            return URL_BASE + "?" + urlencode({"MakeIds[0]": marca, "pg": pagina})
        return URL_BASE
    except:
        return URL_BASE


def save_state(page_url):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    parsed = urlparse(page_url)
    params = parse_qs(parsed.query)
    state = {
        "marca": int(params.get("MakeIds[0]", ["0"])[0]),
        "pagina": params.get("pg", ["1"])[0],
        "min": min_wait, "max": max_wait
    }
    with open(os.path.join(CONFIG_DIR, "state.json"), "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4, ensure_ascii=False)


def get_incomplete_ads():
    data_dir = Path(DATA_DIR)
    if not data_dir.exists():
        return []
    incomplete = []
    for file in sorted(data_dir.glob("*.json"), key=lambda p: int(p.stem) if p.stem.isdigit() else 0):
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("extendido", "N") not in ["S", "NO DISPONIBLE"]:
                incomplete.append(data)
        except:
            pass
    return incomplete


def get_ads_stats():
    data_dir = Path(DATA_DIR)
    stats = {"total": 0, "extendidos": 0, "pendientes": 0, "no_disponibles": 0}
    if not data_dir.exists():
        return stats
    files = list(data_dir.glob("*.json"))
    stats["total"] = len(files)
    for file in files:
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
            ext = data.get("extendido", "N")
            if ext == "S": stats["extendidos"] += 1
            elif ext == "NO DISPONIBLE": stats["no_disponibles"] += 1
            else: stats["pendientes"] += 1
        except:
            pass
    return stats


# =============================================================================
# COOKIES Y NAVEGACION
# =============================================================================

async def accept_cookies(page):
    try:
        cookie_button = page.locator("#didomi-notice-agree-button")
        if await cookie_button.is_visible(timeout=3000):
            await cookie_button.click()
            await asyncio.sleep(random.uniform(1, 2))
            print("Cookies aceptadas")
            return True
    except:
        pass
    return False


async def init_browser_session(browser):
    page = await browser.new_page()
    
    print("Iniciando sesion...")
    await page.goto("https://www.coches.net/", wait_until="load")
    await asyncio.sleep(random.uniform(2, 5))
    await accept_cookies(page)
    await asyncio.sleep(random.uniform(3, 7))
    
    # Scroll inicial
    for _ in range(random.randint(2, 5)):
        await page.mouse.wheel(0, random.uniform(200, 500))
        await asyncio.sleep(random.uniform(0.8, 2.0))
    
    if await is_blocked(page):
        print("BLOQUEADO en pagina principal")
        await page.screenshot(path="blocked_main.png")
        return None
    
    print("Sesion iniciada correctamente")
    return page


async def click_first_ad(page):
    """Pulsa el primer anuncio del listado"""

    selectors = ['div.mt-ListAds-item[data-ad-position]','div.mt-ListAds-item[data-ad-position="0"]']

    for selector in selectors:
        try:
            await page.wait_for_selector(selector, timeout=15000)
            
            first_ad = page.locator(selector).first

            if not first_ad:
                print("No se encontro el primer anuncio")
                return False
            
            link = first_ad.locator("a.mt-CardAd-infoHeaderTitleLink")
            
            if await link.count() > 0:
                print("Pulsando primer anuncio...")
                await link.click()
                await asyncio.sleep(random.uniform(2, 4))
                return True

            return False
        except Exception as e:
            print(f"Error pulsando primer anuncio: {e}")
            return False


async def click_next_ad(page):
    """Pulsa el botón 'Siguiente' en la página de detalle del anuncio"""
    selectors = [
        'a[title="Siguiente"]',
        'a.sui-AtomButton--circular[title="Siguiente"]',
        'button[title="Siguiente"]',
        'div.mt-NavigationAdToolbar-actions a[title="Siguiente"]',
        'ul.mt-NavigationActions li:last-child a',
    ]
    #.sui-AtomButton--disabled
    
    for selector in selectors:
        locator = page.locator(selector)
        if await locator.count() > 0:
            try:
                is_disabled = await locator.get_attribute("aria-disabled")
                if is_disabled == "true":
                    print("Botón Siguiente deshabilitado (último anuncio)")
                    return False
                
                href = await locator.get_attribute("href")
                if href:
                    print(f"Siguiente: ...{href[-50:]}")
                    await locator.click()
                    await asyncio.sleep(random.uniform(2, 4))
                    return True
            except Exception as e:
                print(f"Error con selector {selector}: {e}")
                continue
    
    print("Botón Siguiente no encontrado")
    return False


async def click_next_page(page):
    """Click en siguiente página del listado"""
    print("Click en siguiente pagina")
    
    selector = 'a[aria-label="Página siguiente"]'
    locator = page.locator(selector)
    
    if await locator.count() == 0:
        print("Botón no encontrado, volviendo a la pagina base")
        selector = 'a[aria-label="Volver"]'
        locator = page.locator(selector)
        global paginas
        paginas = paginas + 1
        #return False
    
    disabled = await locator.get_attribute("aria-disabled")
    if disabled == "true":
        print("Botón deshabilitado (última pagina)")
        return False
    
    try:
        await locator.click()
        await asyncio.sleep(random.uniform(2, 4))
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False


# =============================================================================
# SCRAPING
# =============================================================================

async def scrape_page(page):
    """Scrapea los anuncios de la página actual del listado"""
    try:
        await page.wait_for_selector("div.mt-ListAds-item[data-ad-position]", timeout=20000)
    except:
        return []
    
    await human_scroll(page)
    items = page.locator("div.mt-ListAds-item[data-ad-position]")
    count = await items.count()
    print("Items:", count)
    
    results = []
    for i in range(count):
        result = await obtain_info(items.nth(i))
        if result:
            results.append(result)
            save_item(result)
    return results


async def scrape_all_pages(page):
    """Scrapea todas las páginas del listado"""
    global paginas
    pages_scraped = 0
    
    while True:
        parsed = urlparse(page.url)
        params = parse_qs(parsed.query)
        print("pagina:", params.get("pg", ["1"])[0])
        
        if await is_blocked(page):
            print("BLOQUEADO")
            await page.screenshot(path="blocked.png")
            save_state(page.url)
            break
        
        await random_delay(min_wait, max_wait)
        await scrape_page(page)
        
        pages_scraped += 1
        paginas += 1
        save_state(page.url)
        
        if pages_scraped % 5 == 0:
            await random_delay(8000, 15000)
        
        if not await click_next_page(page):
            print("Fin del listado")
            break
        
        await asyncio.sleep(random.uniform(2, 4))


# =============================================================================
# MODOS PRINCIPALES
# =============================================================================

async def run_scraper_basic():
    """Modo 1: Scraping basico (solo listados)"""
    global hits, paginas
    hits = paginas = 0
    print("\nIniciando scraper basico\n" + "=" * 50)
    start_time = time.time()
    
    async with AsyncCamoufox(headless=HEADLESS, geoip=True, humanize=True, block_images=False, block_webrtc=True, os=("windows", "macos", "linux")) as browser:
        page = await init_browser_session(browser)
        if not page:
            return
        
        url = load_state()
        print("URL:", url)
        await page.goto(url, wait_until="domcontentloaded")
        await accept_cookies(page)
        
        if await is_blocked(page):
            print("BLOQUEADO")
            save_state(page.url)
            return
        
        await random_delay(3000, 6000)
        await scrape_all_pages(page)
    
    print_summary(start_time)


async def run_scraper_extended():
    """
    Modo 2: Scraper extendido navegando entre anuncios.
    - Entra al primer anuncio del listado
    - Navega con el botón "Siguiente" entre anuncios
    - Extrae info completa de cada uno
    - Continúa hasta alcanzar MAX_REQUESTS_PER_SESSION o ser bloqueado
    """
    global hits, paginas, anuncios_extendidos, no_disponibles, session_requests
    hits = paginas = anuncios_extendidos = no_disponibles = 0
    session_requests = 0
    
    print("\nIniciando scraper extendido (navegación por anuncios)\n" + "=" * 50)
    print(f"Límite configurado: {MAX_REQUESTS_PER_SESSION} anuncios")
    start_time = time.time()
    
    async with AsyncCamoufox(headless=HEADLESS, geoip=True, humanize=True, block_images=False, block_webrtc=True, os=("windows", "macos", "linux")) as browser:
        page = await init_browser_session(browser)
        if not page:
            return
        
        # Ir al listado
        url = load_state()
        print(f"URL listado: {url}")
        await page.goto(url, wait_until="load", timeout=60000)
        await accept_cookies(page)
        
        if await is_blocked(page):
            print("BLOQUEADO en listado")
            save_state(page.url)
            return
        
        await random_delay(min_wait, max_wait)
        
        # Hacer scroll para cargar anuncios
        await human_scroll(page)
        
        # Pulsar el primer anuncio
        if not await click_first_ad(page):
            print("No se pudo pulsar el primer anuncio")
            return
        
        # Aceptar cookies si aparecen en detalle
        await accept_cookies(page)
        await random_delay(min_wait, max_wait)
        
        # Bucle principal: navegar entre anuncios hasta el límite
        ads_processed = 0
        
        while ads_processed < MAX_REQUESTS_PER_SESSION:
            ads_processed += 1
            print(f"\n--- Anuncio #{ads_processed}/{MAX_REQUESTS_PER_SESSION} ---")
            
            # Verificar bloqueo
            if await is_blocked(page):
                print("BLOQUEADO")
                save_state(page.url)
                break
            
            # Extraer información del anuncio actual
            result = await obtain_extended_info_from_detail(page)
            
            if result:
                save_item(result)
            
            # Verificar si hemos llegado al límite
            if ads_processed >= MAX_REQUESTS_PER_SESSION:
                print(f"\nLímite de {MAX_REQUESTS_PER_SESSION} anuncios alcanzado")
                break
            
            # Pausa entre anuncios (sin el control de sesión ya que lo hacemos aquí)
            base_delay = random.uniform(min_wait, max_wait)
            if random.random() < 0.25:
                base_delay += random.uniform(min_wait, max_wait)
                print("Pausa extra entre anuncios")
            if random.random() < 0.10:
                base_delay += random.uniform(min_wait, max_wait)
                print("Pausa larga (distraccion)")
            await asyncio.sleep(base_delay / 1000)
            
            # Simular interacción ocasional
            if random.random() < 0.3:
                await simulate_page_interaction(page)
            
            # Ir al siguiente anuncio
            if not await click_next_ad(page):
                await random_delay(min_wait, max_wait)
                await click_next_page(page)
                # await page.pause()
            
                await click_first_ad(page)
                paginas += 1
                #break
            
            # Aceptar cookies si reaparecen
            await accept_cookies(page)
            
            # Espera para que cargue la página
            await random_delay(min_wait, max_wait)
    
    print_summary(start_time)

#Modo 3: Completar anuncios pendientes
async def run_complete_ads():
    global hits, anuncios_extendidos, no_disponibles, session_requests
    hits = anuncios_extendidos = no_disponibles = 0
    session_requests = 0
    
    print("\nIniciando completar anuncios\n" + "=" * 50)
    
    incomplete = get_incomplete_ads()
    if not incomplete:
        print("TODOS LOS ANUNCIOS COMPLETOS")
        return
    
    print("anuncios por completar:", len(incomplete))
    start_time = time.time()
    
    # Mezclar orden
    if random.random() < 0.6:
        random.shuffle(incomplete)
        print("Orden aleatorio activado")
    
    async with AsyncCamoufox(headless=HEADLESS, geoip=True, humanize=True, block_images=False, block_webrtc=True, os=("windows", "macos", "linux")) as browser:
        page = await init_browser_session(browser)
        if not page:
            return
        
        load_state()
        completados = 0
        errores = 0
        
        for i, ad in enumerate(incomplete):
            print(f"\n[{i+1}/{len(incomplete)}] Anuncio {ad.get('id')}")
            
            if i > 0 and i % 5 == 0:
                if await is_blocked(page):
                    print("BLOQUEADO - Deteniendo")
                    page.pause()
            
            # Navegar al anuncio
            print(ad)
            url = ad.get('url', '')
            if isinstance(url, list):
                url = url[0]

            if not url.startswith("http"):
                url = "https://www.coches.net/" + url.lstrip("/")
            
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                print(f"Error navegando: {e}")
                errores += 1
                continue
            
            await accept_cookies(page)
            await random_delay(2000, 5000)
            
            # Extraer info
            result = await obtain_extended_info_from_detail(page)
            
            if result:
                # Mantener datos del resultado original si faltan
                for key in ad:
                    if key not in result or result[key] is None:
                        result[key] = ad[key]
                
                save_item(result)
                if result.get("extendido") == "S":
                    completados += 1
            else:
                errores += 1
            
            await delay_between_ads()
            
            if random.random() < 0.3:
                await simulate_page_interaction(page)
        
        print(f"\nResumen: Extendidos={completados}, No disponibles={no_disponibles}, Errores={errores}")
    
    print_summary(start_time)


def print_summary(start_time):
    total_time = time.time() - start_time
    print(f"\n{'='*50}\nResumen: {total_time:.1f}s ({total_time/60:.1f}min)")
    print(f"Paginas: {paginas}, Guardados: {hits}, Extendidos: {anuncios_extendidos}, No disponibles: {no_disponibles}\n{'='*50}")


# =============================================================================
# MENU
# =============================================================================

def show_menu():
    print(f"\n{'='*50}\nSCRAPER COCHES.NET\n{'='*50}")
    stats = get_ads_stats()
    print(f"\nTotal: {stats['total']}, Extendidos: {stats['extendidos']}, Pendientes: {stats['pendientes']}, No disponibles: {stats['no_disponibles']}")
    print(f"\nConfig: MaxReq={MAX_REQUESTS_PER_SESSION}, Pausa={SESSION_PAUSE_MIN/1000:.0f}-{SESSION_PAUSE_MAX/1000:.0f}s, Espera={min_wait/1000:.0f}-{max_wait/1000:.0f}s")
    print("\n1. Scraping basico (listados)")
    print("2. Scraping extendido (navegar anuncios)")
    print("3. Completar anuncios pendientes")
    print("4. Configurar")
    print("5. Insertar anuncios extendidos en DB")
    print("0. Salir\n")
    return input("Opcion: ").strip()


def configure_timing():
    global MAX_REQUESTS_PER_SESSION, SESSION_PAUSE_MIN, SESSION_PAUSE_MAX, min_wait, max_wait
    print(f"\n{'='*50}\nCONFIGURACION\n{'='*50}")
    print(f"1. Max peticiones: {MAX_REQUESTS_PER_SESSION}")
    print(f"2. Pausa min sesion: {SESSION_PAUSE_MIN/1000:.0f}s")
    print(f"3. Pausa max sesion: {SESSION_PAUSE_MAX/1000:.0f}s")
    print(f"4. Espera min: {min_wait/1000:.0f}s")
    print(f"5. Espera max: {max_wait/1000:.0f}s")
    print(f"6. Modo solo terminal")
    print("\nPresets: A=Agresivo, N=Normal, C=Cauteloso, U=Ultra-cauteloso, X=Volver")
    
    op = input("\nOpcion: ").strip().upper()
    
    presets = {
        "A": (1000000, 750, 2000, 750, 2000),
        "N": (1000000, 1000, 3000, 1000, 3000),
        "C": (500, 120000, 300000, 10000, 25000),
        "U": (50, 180000, 420000, 15000, 40000),
    }
    
    try:
        if op in presets:
            MAX_REQUESTS_PER_SESSION, SESSION_PAUSE_MIN, SESSION_PAUSE_MAX, min_wait, max_wait = presets[op]
            print(f"Preset {op} aplicado")
        elif op in "12345":
            
                valor = int(input("Nuevo valor: "))
                if op == "1": MAX_REQUESTS_PER_SESSION = valor
                elif op == "2": SESSION_PAUSE_MIN = valor * 1000
                elif op == "3": SESSION_PAUSE_MAX = valor * 1000
                elif op == "4": min_wait = valor * 1000
                elif op == "5": max_wait = valor * 1000
        elif op in "6":
            global HEADLESS
            HEADLESS = True
            print("Modo solo terminal activado (HEADLESS=True)")    
    except:
        print("Valor invalido")

#INSERTAR ANUNCIOS EXTENDIDOS EN LA BASE DE DATOS

class CochesDBLoader:
    def __init__(self, dbname="anuncios", user="postgres", password=None):
        self.conn = psycopg2.connect(
            dbname=dbname,
            user=user,
            password=password,
            host="localhost",
            port="5432"
        )
        self.create_tables()


    #Crea tablas e índices
    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS anuncios (
                id VARCHAR PRIMARY KEY,
                brand VARCHAR(50),
                model VARCHAR(200),
                price INTEGER,
                original_price INTEGER,
                year INTEGER,
                km INTEGER,
                cv INTEGER,
                cc INTEGER,
                fuel VARCHAR(50),
                transmission VARCHAR(50),
                doors INTEGER,
                seats INTEGER,
                car_type VARCHAR(50),
                location VARCHAR(100),
                label VARCHAR(100),
                comments TEXT,
                url VARCHAR(500),
                extendido VARCHAR(20),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
            
            CREATE INDEX IF NOT EXISTS idx_brand ON anuncios(brand);
            CREATE INDEX IF NOT EXISTS idx_price ON anuncios(price);
            CREATE INDEX IF NOT EXISTS idx_year ON anuncios(year);
            CREATE INDEX IF NOT EXISTS idx_brand_year ON anuncios(brand, year);
        """)
        self.conn.commit()

    #Carga todos los JSONs en batches
    def load_from_json_dir(self, data_dir="data/", batch_size=1000):
        data_path = Path(data_dir)
        files = list(data_path.glob("*.json"))
        total = len(files)
        
        print(f"Encontrados {total} archivos JSON")
        
        batch = []
        loaded = 0
        start_time = time.time()
        
        for i, file in enumerate(files, 1):
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    ad = json.load(f)
                    
                    if ad.get('extendido') == 'S':
                        # completo las ubiaciones e los anuncios mal extendidas
                        if ad.get('location') is None:
                            location =  re.search(r"-en-([a-zA-Z\-]+)-\d+", ad.get('url'))
                            if location:
                                location = location.group(1)
                            else:
                                location = "desconocida"
                            ad['location'] = location
                        batch.append(ad)
                        if len(batch) >= batch_size:
                            self._insert_batch(batch)
                            loaded += len(batch)
                            batch = []
                            print(f"{loaded}/{total} ({loaded/total*100:.1f}%)")
            
            except Exception as e:
                print(f"Error en {file}: {e}")
        
        # Insertar último batch
        if batch:
            self._insert_batch(batch)
            loaded += len(batch)
        
        elapsed = time.time() - start_time
        print(f"\n{loaded} anuncios cargados en {elapsed:.2f}s ({loaded/elapsed:.0f} ads/s)")
        self.print_stats()

    #Inserta batch con UPSERT
    def _insert_batch(self, ads):
        
        cursor = self.conn.cursor()
        
        values = [
            (
                ad.get('id'), ad.get('brand'), ad.get('model'),
                ad.get('price'), ad.get('original_price'), ad.get('year'),
                ad.get('km'), ad.get('cv'), ad.get('cc'),
                ad.get('fuel'), ad.get('transmission'), ad.get('doors'),
                ad.get('seats'), ad.get('type'), ad.get('location'),
                ad.get('label'), ad.get('comments'), ad.get('url'),
                ad.get('extendido')
            )
            for ad in ads
        ]
        
        execute_values(
            cursor,
            """
            INSERT INTO anuncios (id, brand, model, price, original_price, year, km, cv, cc,
                             fuel, transmission, doors, seats, car_type, location, label,
                             comments, url, extendido)
            VALUES %s
            ON CONFLICT (id) DO UPDATE SET
                price = EXCLUDED.price,
                km = EXCLUDED.km,
                updated_at = NOW()
            """,
            values
        )
        
        self.conn.commit()
    
    #Imprime estadísticas de la DB
    def print_stats(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                AVG(price)::INTEGER as avg_price,
                COUNT(DISTINCT brand) as brands
            FROM anuncios
        """)
        
        total, avg_price, brands = cursor.fetchone()
        print(f"\nEstadísticas:")
        print(f"Total anuncios: {total:,}")
        print(f"Precio medio: {avg_price:,}€")
        print(f"Marcas únicas: {brands}")
    
    def close(self):
        self.conn.close()


async def main():
    if not CAMOUFOX_AVAILABLE:
        print("Camoufox no instalado\npip install camoufox --break-system-packages\ncamoufox fetch")
        return
    
    while True:
        op = show_menu()
        if op == "1": await run_scraper_basic()
        elif op == "2": await run_scraper_extended()
        elif op == "3": await run_complete_ads()
        elif op == "4": configure_timing()
        elif op == "5": 
            with open(DB_CONFIG_FILE, 'r') as f:
                config = json.load(f)

            loader = CochesDBLoader(password=config["password"])
            loader.load_from_json_dir(DATA_DIR)
            loader.close()
        elif op == "0": print("\nFIN"); break


if __name__ == "__main__":
    asyncio.run(main())