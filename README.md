# 🛒 Monitor de Precios con Bot de Telegram

Bot que monitorea precios de productos en múltiples tiendas online y envía alertas automáticas a Telegram cuando detecta drops de precio o cambios de stock.

## ✨ Características

- 🏪 **Multi-store**: MercadoLibre, Amazon, HardGamers, Garbarino, Fravega, Musimundo y más
- 🤖 **Scraping inteligente**: BeautifulSoup primero → Playwright como fallback automático
- 📊 **Gráficos de evolución** de precios con estilo oscuro tipo trading
- 🔥 **Alertas de drops**: Notificación instantánea cuando el precio baja X%
- 🟢 **Alertas de stock**: Aviso cuando un producto vuelve a estar disponible
- ⏰ **Chequeo automático** cada N horas (configurable)
- 💾 **Historial persistente** en SQLite

---

## 🚀 Instalación

### 1. Clonar / descomprimir el proyecto

```bash
cd price-monitor
```

### 2. Crear entorno virtual e instalar dependencias

```bash
python -m venv venv
source venv/bin/activate        # Linux/Mac
# ó
venv\Scripts\activate           # Windows

pip install -r requirements.txt
```

### 3. Instalar Playwright y sus browsers

```bash
playwright install chromium
```

### 4. Configurar variables de entorno

```bash
cp .env.example .env
# Editá el archivo .env con tu editor favorito
```

Contenido de `.env`:
```env
TELEGRAM_BOT_TOKEN=123456789:ABCdef...   # Token de @BotFather
TELEGRAM_CHAT_ID=-1001234567890          # ID de tu chat o grupo
PRICE_DROP_THRESHOLD_PERCENT=5           # Alertar si baja 5% o más
CHECK_INTERVAL_HOURS=1                   # Chequear cada 1 hora
SCRAPE_DELAY_SECONDS=3                   # Pausa entre requests
```

#### Cómo obtener el token de Telegram:
1. Abrí Telegram y buscá `@BotFather`
2. Enviá `/newbot` y seguí las instrucciones
3. Copiá el token que te da

#### Cómo obtener tu Chat ID:
1. Buscá `@userinfobot` en Telegram
2. Enviá `/start` → te dice tu ID
3. Para grupos: agregá el bot al grupo y usá `/id` ó buscá con `@RawDataBot`

---

## 🤖 Uso del Bot

### Arrancar el bot

```bash
python telegram_bot.py
```

### Comandos disponibles en Telegram

| Comando | Descripción |
|---|---|
| `/agregar URL` | Agrega un producto al monitoreo |
| `/agregar URL Nombre` | Agrega con nombre personalizado |
| `/lista` | Muestra todos los productos con precios |
| `/precio ID` | Muestra gráfico de evolución del precio |
| `/chequear` | Fuerza un chequeo inmediato de todos los productos |
| `/eliminar ID` | Deja de monitorear un producto |
| `/ayuda` | Muestra la ayuda |

### Ejemplos de uso

```
/agregar https://www.mercadolibre.com.ar/rtx-4070-...
/agregar https://www.amazon.com/dp/B0XXXXX RTX 4070 Super
/precio 3
/eliminar 1
```

---

## 🖥️ Gestión por línea de comandos

También podés gestionar productos sin usar el bot:

```bash
# Agregar un producto
python manage.py agregar https://www.mercadolibre.com.ar/...

# Agregar con nombre
python manage.py agregar https://... --nombre "RTX 4070 Super"

# Ver lista de productos
python manage.py lista

# Chequear precios ahora
python manage.py chequear

# Eliminar producto
python manage.py eliminar 3
```

---

## 📊 Tiendas soportadas

| Tienda | Soporte |
|---|---|
| MercadoLibre | ✅ Parser dedicado |
| Amazon (.com / .com.mx) | ✅ Parser dedicado |
| HardGamers | ✅ Parser dedicado |
| Garbarino | ✅ Parser genérico |
| Fravega | ✅ Parser genérico |
| Musimundo | ✅ Parser genérico |
| Full H4rd | ✅ Parser genérico |
| Cualquier tienda | ⚡ Parser genérico + Playwright |

> **¿Tu tienda no está?** Podés agregar un parser en `scraper.py` siguiendo el patrón de los existentes.

---

## 🏗️ Estructura del proyecto

```
price-monitor/
├── telegram_bot.py   # Bot principal + comandos + scheduler
├── scraper.py        # Motor de scraping (BS4 + Playwright)
├── charts.py         # Generación de gráficos matplotlib
├── database.py       # SQLite: guardar y leer precios
├── manage.py         # CLI para gestión sin bot
├── requirements.txt  # Dependencias Python
├── .env.example      # Plantilla de configuración
└── README.md         # Este archivo
```

---

## ⚙️ Cómo funciona el fallback de scraping

```
URL del producto
      │
      ▼
┌─────────────────────┐
│  BeautifulSoup      │  → Rápido, sin browser, bajo consumo
│  + requests         │
└──────────┬──────────┘
           │ ¿Encontró precio? 
     NO ───┘
      │
      ▼
┌─────────────────────┐
│  Playwright         │  → Browser headless real, maneja JS
│  (Chromium)         │
└──────────┬──────────┘
           │
      ¿Encontró precio?
      SÍ → Guardar + Alertar
      NO → Loggear error
```

---

## 🔔 Tipos de alertas

### Drop de precio
Se envía cuando el precio baja más del umbral configurado (`PRICE_DROP_THRESHOLD_PERCENT`):

```
🔥 ¡DROP DE PRECIO!

🛒 RTX 4070 Super - Palit

❌ Antes: $850.000
✅ Ahora: $790.000
💸 Ahorrás: $60.000 (-7.1%)

¡Comprar ahora! [link]
```
+ Gráfico de evolución del precio adjunto

### Volvió al stock
```
🟢 ¡Volvió al stock!
📦 RTX 4070 Super - Palit
💰 Precio: $790.000
Ver en tienda [link]
```

---

## 📝 Agregar soporte para una nueva tienda

En `scraper.py`, agregá una función de parser:

```python
def parse_mi_tienda(soup: BeautifulSoup, url: str) -> dict:
    result = {"price": None, "currency": "ARS", "in_stock": True, "name": ""}
    
    # Buscar el nombre del producto
    name_tag = soup.find("h1", class_="product-name")
    if name_tag:
        result["name"] = name_tag.get_text(strip=True)
    
    # Buscar el precio
    price_tag = soup.find("span", class_="precio-actual")
    if price_tag:
        result["price"] = parse_price_text(price_tag.get_text(strip=True))
    
    return result
```

Luego registrala en `PARSERS` y en `detect_store()`.

---

## 🐳 Docker (opcional)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt && playwright install chromium --with-deps
COPY . .
CMD ["python", "telegram_bot.py"]
```

---

## ⚠️ Consideraciones legales y éticas

- Respetá el `robots.txt` de cada sitio
- Usá delays razonables entre requests (`SCRAPE_DELAY_SECONDS`)
- No hagas scraping masivo ni agresivo
- Algunos sitios bloquean scrapers; Playwright ayuda pero no es infalible
