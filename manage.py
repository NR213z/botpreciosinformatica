"""
manage.py - Herramienta CLI para gestionar productos sin usar el bot
"""

import sys
import argparse
import database as db
from scraper import scrape_product, detect_store


def cmd_add(args):
    url = args.url
    store = detect_store(url)
    name_override = args.nombre

    print(f"🔍 Scrapeando: {url[:60]}...")
    temp = {"id": 0, "name": name_override or "Nuevo producto", "url": url, "store": store}
    result = scrape_product(temp)

    name = name_override or result.name or f"Producto de {store}"
    product_id = db.add_product(name, url, store)

    if result.price:
        db.save_price(product_id, result.price, result.currency, result.in_stock)
        print(f"💰 Precio registrado: {result.currency} {result.price:,.2f}")
    else:
        print("⚠️  No se pudo obtener el precio ahora, se reintentará en el próximo chequeo.")

    print(f"✅ Producto agregado con ID: {product_id}")


def cmd_list(args):
    products = db.get_active_products()
    if not products:
        print("📋 No hay productos monitoreados.")
        return

    print(f"\n{'ID':<5} {'Tienda':<15} {'Nombre':<40} {'Último precio':<15}")
    print("-" * 80)
    for p in products:
        last = db.get_last_price(p["id"])
        price_str = f"{last['currency']} {last['price']:,.0f}" if last and last["price"] else "Sin datos"
        print(f"{p['id']:<5} {p['store']:<15} {p['name'][:39]:<40} {price_str:<15}")


def cmd_remove(args):
    db.remove_product(args.id)
    print(f"🗑️  Producto {args.id} eliminado.")


def cmd_check(args):
    products = db.get_active_products()
    if not products:
        print("📋 No hay productos.")
        return

    for p in products:
        result = scrape_product(p)
        if result.price:
            last = db.get_last_price(p["id"])
            db.save_price(p["id"], result.price, result.currency, result.in_stock)
            change = ""
            if last and last["price"]:
                pct = ((result.price - last["price"]) / last["price"]) * 100
                change = f"  ({pct:+.1f}%)"
            stock = "✅" if result.in_stock else "❌"
            print(f"{stock} {p['name'][:40]} — {result.currency} {result.price:,.0f}{change}")
        else:
            print(f"⚠️  {p['name'][:40]} — No se pudo obtener precio")


def main():
    db.init_db()
    parser = argparse.ArgumentParser(description="🛒 Monitor de Precios - Gestión CLI")
    subparsers = parser.add_subparsers(dest="command")

    # Agregar
    p_add = subparsers.add_parser("agregar", help="Agregar un producto")
    p_add.add_argument("url", help="URL del producto")
    p_add.add_argument("--nombre", "-n", help="Nombre personalizado", default="")
    p_add.set_defaults(func=cmd_add)

    # Listar
    p_list = subparsers.add_parser("lista", help="Listar productos")
    p_list.set_defaults(func=cmd_list)

    # Eliminar
    p_rm = subparsers.add_parser("eliminar", help="Eliminar un producto")
    p_rm.add_argument("id", type=int, help="ID del producto")
    p_rm.set_defaults(func=cmd_remove)

    # Chequear
    p_check = subparsers.add_parser("chequear", help="Chequear precios ahora")
    p_check.set_defaults(func=cmd_check)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
