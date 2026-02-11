"""
database.py - Manejo de SQLite para persistencia de precios
"""

import sqlite3
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DB_FILE = os.getenv("DB_FILE", "prices.db")


def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Crea las tablas si no existen."""
    conn = get_connection()
    cursor = conn.cursor()

    # Tabla de productos monitoreados
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            url         TEXT NOT NULL UNIQUE,
            store       TEXT NOT NULL,
            active      INTEGER DEFAULT 1,
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)

    # Tabla de historial de precios
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id  INTEGER NOT NULL,
            price       REAL,
            currency    TEXT DEFAULT 'ARS',
            in_stock    INTEGER DEFAULT 1,
            checked_at  TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)

    conn.commit()
    conn.close()
    print("✅ Base de datos inicializada.")


def add_product(name: str, url: str, store: str) -> int:
    """Agrega un producto a monitorear. Retorna el ID."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO products (name, url, store) VALUES (?, ?, ?)",
            (name, url, store)
        )
        conn.commit()
        product_id = cursor.lastrowid
        print(f"✅ Producto agregado: {name} (ID: {product_id})")
        return product_id
    except sqlite3.IntegrityError:
        # Ya existe, devolver el ID existente
        cursor.execute("SELECT id FROM products WHERE url = ?", (url,))
        row = cursor.fetchone()
        print(f"⚠️  Producto ya existe con ID: {row['id']}")
        return row["id"]
    finally:
        conn.close()


def get_active_products() -> list:
    """Retorna todos los productos activos."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE active = 1")
    products = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return products


def save_price(product_id: int, price: float, currency: str = "ARS", in_stock: bool = True):
    """Guarda un registro de precio en el historial."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO price_history (product_id, price, currency, in_stock) VALUES (?, ?, ?, ?)",
        (product_id, price, currency, 1 if in_stock else 0)
    )
    conn.commit()
    conn.close()


def get_price_history(product_id: int, limit: int = 168) -> list:
    """
    Retorna el historial de precios de un producto.
    Por defecto las últimas 168 horas (7 días).
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT price, currency, in_stock, checked_at
        FROM price_history
        WHERE product_id = ?
        ORDER BY checked_at ASC
        LIMIT ?
    """, (product_id, limit))
    history = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return history


def get_last_price(product_id: int) -> dict | None:
    """Retorna el último precio registrado para un producto."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT price, currency, in_stock, checked_at
        FROM price_history
        WHERE product_id = ?
        ORDER BY checked_at DESC
        LIMIT 1
    """, (product_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def remove_product(product_id: int):
    """Desactiva un producto (soft delete)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE products SET active = 0 WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()
    print(f"🗑️  Producto {product_id} desactivado.")
