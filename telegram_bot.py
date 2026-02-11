"""
telegram_bot.py - Bot de Telegram con comandos y notificaciones automáticas
"""

import os
import io
import logging
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)
from telegram.constants import ParseMode

import database as db
import charts
from scraper import scrape_product, detect_store

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DROP_THRESHOLD = float(os.getenv("PRICE_DROP_THRESHOLD_PERCENT", 5))
CHECK_INTERVAL_HOURS = int(os.getenv("CHECK_INTERVAL_HOURS", 1))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  UTILIDADES
# ─────────────────────────────────────────────

def format_price(price: float, currency: str = "ARS") -> str:
    if currency == "ARS":
        return f"${price:,.0f}".replace(",", ".")
    return f"${price:,.2f} {currency}"


def store_emoji(store: str) -> str:
    emojis = {
        "mercadolibre": "🛒",
        "amazon": "📦",
        "hardgamers": "🎮",
        "garbarino": "🏠",
        "fravega": "🛍️",
        "musimundo": "🎵",
        "fullh4rd": "💻",
        "generic": "🌐",
    }
    return emojis.get(store.lower(), "🏪")


async def send_price_chart(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: str,
    product: dict,
    caption: str = ""
):
    """Envía el gráfico de precios como imagen al chat."""
    history = db.get_price_history(product["id"])
    last = db.get_last_price(product["id"])
    currency = last.get("currency", "ARS") if last else "ARS"
    current_price = last["price"] if last else None

    image_bytes = charts.generate_price_chart(
        product_name=product["name"],
        store=product["store"],
        history=history,
        current_price=current_price,
        currency=currency
    )
    await context.bot.send_photo(
        chat_id=chat_id,
        photo=io.BytesIO(image_bytes),
        caption=caption,
        parse_mode=ParseMode.HTML
    )


# ─────────────────────────────────────────────
#  COMANDOS
# ─────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 <b>Bienvenido al Monitor de Precios</b>\n\n"
        "Comandos disponibles:\n"
        "➕ /agregar <code>URL</code> — Agregar producto a monitorear\n"
        "📋 /lista — Ver todos los productos\n"
        "📊 /precio <code>ID</code> — Ver gráfico de evolución\n"
        "🔍 /chequear — Chequear precios ahora\n"
        "🗑️ /eliminar <code>ID</code> — Dejar de monitorear\n"
        "ℹ️ /ayuda — Ver esta ayuda\n\n"
        "Enviame un link de producto para agregarlo directamente!"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, context)


async def cmd_agregar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Agrega un nuevo producto. Uso: /agregar URL [nombre opcional]"""
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Uso: <code>/agregar https://url-del-producto.com</code>\n"
            "Opcionalmente: <code>/agregar URL Nombre del producto</code>",
            parse_mode=ParseMode.HTML
        )
        return

    url = args[0]
    if not url.startswith("http"):
        await update.message.reply_text("❌ La URL debe empezar con http:// o https://")
        return

    # Nombre opcional
    custom_name = " ".join(args[1:]) if len(args) > 1 else ""

    msg = await update.message.reply_text("⏳ Obteniendo info del producto...")

    store = detect_store(url)
    temp_product = {"id": 0, "name": custom_name or "Nuevo producto", "url": url, "store": store}

    result = scrape_product(temp_product)

    if result.error and not result.price:
        await msg.edit_text(
            f"⚠️ No se pudo obtener el precio automáticamente.\n"
            f"Podés agregarlo igual con un nombre:\n"
            f"<code>/agregar {url} Nombre del Producto</code>",
            parse_mode=ParseMode.HTML
        )
        return

    name = custom_name or result.name or f"Producto de {store}"
    product_id = db.add_product(name, url, store)

    if result.price:
        db.save_price(product_id, result.price, result.currency, result.in_stock)

    stock_text = "✅ En stock" if result.in_stock else "❌ Sin stock"
    price_text = format_price(result.price, result.currency) if result.price else "No disponible"
    emoji = store_emoji(store)

    await msg.edit_text(
        f"{emoji} <b>Producto agregado!</b>\n\n"
        f"📌 <b>{name}</b>\n"
        f"💰 Precio actual: <b>{price_text}</b>\n"
        f"🏪 Tienda: {store.capitalize()}\n"
        f"{stock_text}\n"
        f"🆔 ID: <code>{product_id}</code>\n\n"
        f"Lo voy a chequear cada {CHECK_INTERVAL_HOURS}h.",
        parse_mode=ParseMode.HTML
    )


async def cmd_lista(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista todos los productos monitoreados."""
    products = db.get_active_products()

    if not products:
        await update.message.reply_text(
            "📋 No tenés productos monitoreados.\n"
            "Usá /agregar para empezar!"
        )
        return

    text = "📋 <b>Productos monitoreados:</b>\n\n"
    for p in products:
        last = db.get_last_price(p["id"])
        emoji = store_emoji(p["store"])

        if last:
            price_text = format_price(last["price"], last["currency"])
            stock_icon = "✅" if last["in_stock"] else "❌"
            time_ago = last["checked_at"][:16].replace("T", " ")
            price_line = f"{stock_icon} {price_text} <i>(actualizado: {time_ago})</i>"
        else:
            price_line = "⏳ Sin datos aún"

        text += (
            f"{emoji} <b>{p['name'][:40]}</b>\n"
            f"   {price_line}\n"
            f"   🆔 ID: <code>{p['id']}</code> | /precio_{p['id']}\n\n"
        )

    # Botones inline para ver cada gráfico
    keyboard = [
        [InlineKeyboardButton(
            f"{store_emoji(p['store'])} {p['name'][:20]}...",
            callback_data=f"chart_{p['id']}"
        )]
        for p in products
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)


async def cmd_precio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ver el gráfico de evolución de un producto. Uso: /precio ID"""
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text(
            "❌ Uso: <code>/precio ID</code>\n"
            "Podés ver los IDs con /lista",
            parse_mode=ParseMode.HTML
        )
        return

    product_id = int(args[0])
    products = db.get_active_products()
    product = next((p for p in products if p["id"] == product_id), None)

    if not product:
        await update.message.reply_text(f"❌ No encontré el producto con ID {product_id}")
        return

    msg = await update.message.reply_text("📊 Generando gráfico...")
    last = db.get_last_price(product_id)
    history = db.get_price_history(product_id)

    if not history:
        await msg.edit_text("⏳ Todavía no hay historial de precios para este producto.")
        return

    price_text = format_price(last["price"], last["currency"]) if last else "N/A"
    caption = (
        f"📊 <b>{product['name'][:50]}</b>\n"
        f"💰 Precio actual: <b>{price_text}</b>\n"
        f"🏪 {product['store'].capitalize()} | {len(history)} registros\n"
        f"🔗 <a href='{product['url']}'>Ver en tienda</a>"
    )

    await msg.delete()
    await send_price_chart(context, update.effective_chat.id, product, caption)


async def cmd_chequear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chequea todos los productos ahora mismo."""
    products = db.get_active_products()
    if not products:
        await update.message.reply_text("📋 No tenés productos monitoreados.")
        return

    msg = await update.message.reply_text(
        f"🔍 Chequeando {len(products)} producto(s)... Aguardá un momento."
    )

    results = []
    for product in products:
        result = scrape_product(product)
        if result.price:
            last = db.get_last_price(product["id"])
            db.save_price(product["id"], result.price, result.currency, result.in_stock)

            change = ""
            if last and last["price"]:
                pct = ((result.price - last["price"]) / last["price"]) * 100
                if pct < 0:
                    change = f" 📉 {pct:.1f}%"
                elif pct > 0:
                    change = f" 📈 +{pct:.1f}%"

            emoji = store_emoji(product["store"])
            stock = "✅" if result.in_stock else "❌"
            results.append(
                f"{emoji} {stock} <b>{product['name'][:30]}</b>\n"
                f"   {format_price(result.price, result.currency)}{change}"
            )
        else:
            results.append(f"⚠️ <b>{product['name'][:30]}</b> — Sin precio")

    text = "✅ <b>Chequeo completado:</b>\n\n" + "\n\n".join(results)
    await msg.edit_text(text, parse_mode=ParseMode.HTML)


async def cmd_eliminar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Elimina un producto del monitoreo. Uso: /eliminar ID"""
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text(
            "❌ Uso: <code>/eliminar ID</code>",
            parse_mode=ParseMode.HTML
        )
        return

    product_id = int(args[0])
    products = db.get_active_products()
    product = next((p for p in products if p["id"] == product_id), None)

    if not product:
        await update.message.reply_text(f"❌ No encontré el producto con ID {product_id}")
        return

    db.remove_product(product_id)
    await update.message.reply_text(
        f"🗑️ <b>{product['name']}</b> eliminado del monitoreo.",
        parse_mode=ParseMode.HTML
    )


# ─────────────────────────────────────────────
#  CALLBACK BOTONES INLINE
# ─────────────────────────────────────────────

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("chart_"):
        product_id = int(query.data.replace("chart_", ""))
        products = db.get_active_products()
        product = next((p for p in products if p["id"] == product_id), None)

        if not product:
            await query.edit_message_text("❌ Producto no encontrado.")
            return

        last = db.get_last_price(product_id)
        price_text = format_price(last["price"], last["currency"]) if last else "N/A"
        caption = (
            f"📊 <b>{product['name'][:50]}</b>\n"
            f"💰 Precio actual: <b>{price_text}</b>\n"
            f"🔗 <a href='{product['url']}'>Ver en tienda</a>"
        )
        await send_price_chart(context, query.message.chat_id, product, caption)


# ─────────────────────────────────────────────
#  JOB: CHEQUEO AUTOMÁTICO PROGRAMADO
# ─────────────────────────────────────────────

async def scheduled_check(context: ContextTypes.DEFAULT_TYPE):
    """Job que se ejecuta cada N horas para chequear precios."""
    products = db.get_active_products()
    if not products:
        return

    logger.info(f"[CRON] Chequeando {len(products)} productos...")
    alerts = []

    for product in products:
        result = scrape_product(product)
        if not result.price:
            continue

        last = db.get_last_price(product["id"])
        db.save_price(product["id"], result.price, result.currency, result.in_stock)

        # Detectar drop de precio
        if last and last["price"] and last["price"] > 0:
            pct_change = ((result.price - last["price"]) / last["price"]) * 100

            if pct_change <= -DROP_THRESHOLD:
                # ¡Drop de precio!
                alerts.append({
                    "product": product,
                    "old_price": last["price"],
                    "new_price": result.price,
                    "currency": result.currency,
                    "pct_change": pct_change,
                    "in_stock": result.in_stock,
                })

            # Notificar si vuelve a tener stock
            elif not last["in_stock"] and result.in_stock:
                await context.bot.send_message(
                    chat_id=CHAT_ID,
                    text=(
                        f"🟢 <b>¡Volvió al stock!</b>\n"
                        f"📦 <b>{product['name'][:50]}</b>\n"
                        f"💰 Precio: <b>{format_price(result.price, result.currency)}</b>\n"
                        f"🔗 <a href='{product['url']}'>Ver en tienda</a>"
                    ),
                    parse_mode=ParseMode.HTML
                )

    # Enviar alertas de drops
    for alert in alerts:
        emoji = store_emoji(alert["product"]["store"])
        old = format_price(alert["old_price"], alert["currency"])
        new = format_price(alert["new_price"], alert["currency"])
        savings = format_price(alert["old_price"] - alert["new_price"], alert["currency"])

        caption = (
            f"🔥 <b>¡DROP DE PRECIO!</b>\n\n"
            f"{emoji} <b>{alert['product']['name'][:50]}</b>\n\n"
            f"❌ Antes: <s>{old}</s>\n"
            f"✅ Ahora: <b>{new}</b>\n"
            f"💸 Ahorrás: <b>{savings}</b> ({alert['pct_change']:.1f}%)\n\n"
            f"🔗 <a href='{alert['product']['url']}'>¡Comprar ahora!</a>"
        )

        history = db.get_price_history(alert["product"]["id"])
        image_bytes = charts.generate_price_chart(
            product_name=alert["product"]["name"],
            store=alert["product"]["store"],
            history=history,
            current_price=alert["new_price"],
            currency=alert["currency"]
        )
        await context.bot.send_photo(
            chat_id=CHAT_ID,
            photo=io.BytesIO(image_bytes),
            caption=caption,
            parse_mode=ParseMode.HTML
        )

    # Resumen cada 24hs (cada 24 chequeos si es 1h)
    # (podés descomentar esto si querés resumen diario)
    # await send_daily_summary(context)

    logger.info(f"[CRON] Listo. {len(alerts)} alertas enviadas.")


# ─────────────────────────────────────────────
#  ARRANCAR EL BOT
# ─────────────────────────────────────────────

def run_bot():
    db.init_db()

    app = Application.builder().token(TOKEN).build()

    # Comandos
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("ayuda", cmd_ayuda))
    app.add_handler(CommandHandler("agregar", cmd_agregar))
    app.add_handler(CommandHandler("lista", cmd_lista))
    app.add_handler(CommandHandler("precio", cmd_precio))
    app.add_handler(CommandHandler("chequear", cmd_chequear))
    app.add_handler(CommandHandler("eliminar", cmd_eliminar))
    app.add_handler(CallbackQueryHandler(button_callback))

    # Job programado
    job_queue = app.job_queue
    job_queue.run_repeating(
        scheduled_check,
        interval=CHECK_INTERVAL_HOURS * 3600,
        first=60,  # primer chequeo al minuto de arrancar
        name="price_check"
    )

    logger.info(f"🤖 Bot iniciado! Chequeando cada {CHECK_INTERVAL_HOURS}h.")
    logger.info(f"📢 Alertando drops de ≥{DROP_THRESHOLD}%")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    run_bot()
