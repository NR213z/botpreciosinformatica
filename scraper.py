"""
scraper.py - Motor de scraping con fallback automático BS4 → Playwright
Soporta: MercadoLibre, Amazon, HardGamers y sitios genéricos
"""

import re
import os
import asyncio
import time
from dataclasses import dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from dotenv import load_dotenv

load_dotenv()

SCRAPE_DELAY = float(os.getenv("SCRAPE_DELAY_SECONDS", 3))
TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 15))

ua = UserAgent()


@dataclass
class ScrapeResult:
    product_id: int
    name: str
    url: str
    store: str
    price: Optional[float]
    currency: str
    in_stock: bool
    error: Optional[str] = None


# ─────────────────────────────────────────────
#  DETECTAR TIENDA DESDE LA URL
# ─────────────────────────────────────────────

def detect_store(url: str) -> str:
    url_lower = url.lower()
    if "mercadolibre" in url_lower or "meli" in url_lower:
        return "mercadolibre"
    elif "amazon" in url_lower:
        return "amazon"
    elif "hardgamers" in url_lower:
        return "hardgamers"
    elif "garbarino" in url_lower:
        return "garbarino"
    elif "fravega" in url_lower:
        return "fravega"
    elif "musimundo" in url_lower:
        return "musimundo"
    elif "fullh4rd" in url_lower:
        return "fullh4rd"
    else:
        return "generic"


# ─────────────────────────────────────────────
#  PARSERS POR TIENDA
# ─────────────────────────────────────────────

def parse_price_text(text: str) -> Optional[float]:
    """Limpia y convierte texto de precio a float."""
    if not text:
        return None
    # Eliminar símbolos de moneda y espacios
    cleaned = re.sub(r'[^\d.,]', '', text.strip())
    # Manejar formato argentino: 1.234.567,89
    if ',' in cleaned and '.' in cleaned:
        if cleaned.rfind(',') > cleaned.rfind('.'):
            cleaned = cleaned.replace('.', '').replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')
    elif ',' in cleaned:
        cleaned = cleaned.replace(',', '.')
    elif cleaned.count('.') > 1:
        cleaned = cleaned.replace('.', '', cleaned.count('.') - 1)
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_mercadolibre(soup: BeautifulSoup, url: str) -> dict:
    result = {"price": None, "currency": "ARS", "in_stock": True, "name": ""}

    # Nombre del producto
    name_tag = (
        soup.find("h1", class_=re.compile(r"ui-pdp-title")) or
        soup.find("h1", class_=re.compile(r"item-title"))
    )
    if name_tag:
        result["name"] = name_tag.get_text(strip=True)

    # Precio principal
    price_tag = (
        soup.find("span", class_=re.compile(r"andes-money-amount__fraction")) or
        soup.find("meta", itemprop="price")
    )
    if price_tag:
        if price_tag.name == "meta":
            result["price"] = parse_price_text(price_tag.get("content", ""))
        else:
            price_text = price_tag.get_text(strip=True)
            # Buscar centavos
            cents_tag = soup.find("span", class_=re.compile(r"andes-money-amount__cents"))
            if cents_tag:
                price_text += "." + cents_tag.get_text(strip=True)
            result["price"] = parse_price_text(price_text)

    # Stock
    no_stock = soup.find(string=re.compile(r"sin stock|agotado|no disponible", re.I))
    if no_stock:
        result["in_stock"] = False

    return result


def parse_amazon(soup: BeautifulSoup, url: str) -> dict:
    result = {"price": None, "currency": "USD", "in_stock": True, "name": ""}

    # Nombre
    name_tag = soup.find("span", id="productTitle")
    if name_tag:
        result["name"] = name_tag.get_text(strip=True)

    # Precio (varios selectores posibles)
    price_selectors = [
        ("span", {"id": "priceblock_ourprice"}),
        ("span", {"id": "priceblock_dealprice"}),
        ("span", {"class": re.compile(r"a-price-whole")}),
        ("span", {"id": "price_inside_buybox"}),
    ]
    for tag, attrs in price_selectors:
        price_tag = soup.find(tag, attrs)
        if price_tag:
            price_text = price_tag.get_text(strip=True)
            # Buscar fracción
            frac_tag = soup.find("span", class_="a-price-fraction")
            if frac_tag and "." not in price_text:
                price_text += "." + frac_tag.get_text(strip=True)
            result["price"] = parse_price_text(price_text)
            if result["price"]:
                break

    # Stock
    unavailable = soup.find(id="outOfStock") or soup.find(string=re.compile(r"unavailable|out of stock", re.I))
    if unavailable:
        result["in_stock"] = False

    # Detectar moneda
    currency_tag = soup.find("span", class_="a-price-symbol")
    if currency_tag:
        symbol = currency_tag.get_text(strip=True)
        if "$" in symbol:
            result["currency"] = "USD"
        elif "€" in symbol:
            result["currency"] = "EUR"

    return result


def parse_hardgamers(soup: BeautifulSoup, url: str) -> dict:
    result = {"price": None, "currency": "ARS", "in_stock": True, "name": ""}

    name_tag = soup.find("h1", class_=re.compile(r"product.*title|title.*product", re.I)) or soup.find("h1")
    if name_tag:
        result["name"] = name_tag.get_text(strip=True)

    price_tag = (
        soup.find("span", class_=re.compile(r"price|precio", re.I)) or
        soup.find("p", class_=re.compile(r"price|precio", re.I))
    )
    if price_tag:
        result["price"] = parse_price_text(price_tag.get_text(strip=True))

    no_stock = soup.find(string=re.compile(r"sin stock|agotado", re.I))
    if no_stock:
        result["in_stock"] = False

    return result


def parse_generic(soup: BeautifulSoup, url: str) -> dict:
    """Parser genérico para tiendas no soportadas explícitamente."""
    result = {"price": None, "currency": "ARS", "in_stock": True, "name": ""}

    # Nombre: meta og:title o h1
    og_title = soup.find("meta", property="og:title")
    if og_title:
        result["name"] = og_title.get("content", "")
    else:
        h1 = soup.find("h1")
        if h1:
            result["name"] = h1.get_text(strip=True)

    # Precio: meta og:price o buscar patrones comunes
    og_price = soup.find("meta", property="product:price:amount")
    if og_price:
        result["price"] = parse_price_text(og_price.get("content", ""))
    else:
        # Buscar elementos con clases que contengan "price" o "precio"
        for tag in soup.find_all(class_=re.compile(r'price|precio', re.I)):
            text = tag.get_text(strip=True)
            price = parse_price_text(text)
            if price and price > 0:
                result["price"] = price
                break

    return result


PARSERS = {
    "mercadolibre": parse_mercadolibre,
    "amazon": parse_amazon,
    "hardgamers": parse_hardgamers,
    "garbarino": parse_generic,
    "fravega": parse_generic,
    "musimundo": parse_generic,
    "fullh4rd": parse_generic,
    "generic": parse_generic,
}


# ─────────────────────────────────────────────
#  SCRAPING CON BS4 (rápido, sin JS)
# ─────────────────────────────────────────────

def scrape_with_bs4(url: str, store: str) -> Optional[dict]:
    """Intenta scraping con requests + BeautifulSoup."""
    headers = {
        "User-Agent": ua.random,
        "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.google.com/",
    }
    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        parser = PARSERS.get(store, parse_generic)
        data = parser(soup, url)
        if data["price"]:
            return data
        print(f"⚠️  BS4 no encontró precio para {url[:60]}...")
        return None
    except Exception as e:
        print(f"❌ BS4 falló: {e}")
        return None


# ─────────────────────────────────────────────
#  SCRAPING CON PLAYWRIGHT (con JS, más robusto)
# ─────────────────────────────────────────────

async def scrape_with_playwright_async(url: str, store: str) -> Optional[dict]:
    """Scraping con Playwright para páginas que requieren JavaScript."""
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=ua.random,
                locale="es-AR",
                extra_http_headers={"Accept-Language": "es-AR,es;q=0.9"}
            )
            page = await context.new_page()

            # Bloquear recursos innecesarios para ser más rápido
            await page.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2}", lambda route: route.abort())

            await page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT * 1000)
            await page.wait_for_timeout(2000)  # Esperar JS dinámico

            content = await page.content()
            await browser.close()

        soup = BeautifulSoup(content, "lxml")
        parser = PARSERS.get(store, parse_generic)
        data = parser(soup, url)
        return data if data["price"] else None

    except Exception as e:
        print(f"❌ Playwright falló: {e}")
        return None


def scrape_with_playwright(url: str, store: str) -> Optional[dict]:
    """Wrapper sincrónico para Playwright."""
    return asyncio.run(scrape_with_playwright_async(url, store))


# ─────────────────────────────────────────────
#  FUNCIÓN PRINCIPAL CON FALLBACK
# ─────────────────────────────────────────────

def scrape_product(product: dict) -> ScrapeResult:
    """
    Intenta scraping con BS4 primero.
    Si falla o no encuentra precio, cae a Playwright.
    """
    url = product["url"]
    store = product.get("store") or detect_store(url)
    product_id = product["id"]
    original_name = product["name"]

    print(f"\n🔍 Scraping: {original_name[:50]}")
    print(f"   Tienda: {store} | URL: {url[:60]}...")

    time.sleep(SCRAPE_DELAY)

    # Intento 1: BeautifulSoup
    print("   → Intentando con BeautifulSoup...")
    data = scrape_with_bs4(url, store)

    # Fallback: Playwright
    if not data or not data.get("price"):
        print("   → Fallback a Playwright...")
        data = scrape_with_playwright(url, store)

    if data and data.get("price"):
        name = data.get("name") or original_name
        print(f"   ✅ Precio: {data['currency']} {data['price']:,.2f} | Stock: {data['in_stock']}")
        return ScrapeResult(
            product_id=product_id,
            name=name,
            url=url,
            store=store,
            price=data["price"],
            currency=data.get("currency", "ARS"),
            in_stock=data.get("in_stock", True),
        )
    else:
        print("   ❌ No se pudo obtener el precio.")
        return ScrapeResult(
            product_id=product_id,
            name=original_name,
            url=url,
            store=store,
            price=None,
            currency="ARS",
            in_stock=False,
            error="No se pudo extraer el precio con BS4 ni Playwright.",
        )
