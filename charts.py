"""
charts.py - Generación de gráficos de evolución de precios con matplotlib
"""

import io
import os
from datetime import datetime
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # Backend sin GUI
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter
import pandas as pd


def format_price_axis(currency: str = "ARS"):
    """Formateador del eje Y según moneda."""
    def formatter(x, pos):
        if x >= 1_000_000:
            return f"${x/1_000_000:.1f}M"
        elif x >= 1_000:
            return f"${x/1_000:.0f}K"
        return f"${x:.0f}"
    return FuncFormatter(formatter)


def generate_price_chart(
    product_name: str,
    store: str,
    history: list,
    current_price: Optional[float] = None,
    currency: str = "ARS"
) -> bytes:
    """
    Genera un gráfico de evolución de precios.
    Retorna los bytes del PNG.
    """
    if not history:
        return _generate_no_data_chart(product_name)

    # Preparar datos
    dates = []
    prices = []
    for entry in history:
        if entry["price"] is not None:
            try:
                dt = datetime.fromisoformat(entry["checked_at"])
            except Exception:
                dt = datetime.now()
            dates.append(dt)
            prices.append(entry["price"])

    if not prices:
        return _generate_no_data_chart(product_name)

    # ── Estilo oscuro tipo "trading" ──
    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#161b22")

    # ── Gradiente bajo la curva ──
    ax.fill_between(dates, prices, alpha=0.15, color="#58a6ff")

    # ── Línea principal ──
    ax.plot(dates, prices, color="#58a6ff", linewidth=2.5, zorder=3)

    # ── Marcar el mínimo y máximo ──
    min_price = min(prices)
    max_price = max(prices)
    min_idx = prices.index(min_price)
    max_idx = prices.index(max_price)

    ax.scatter([dates[min_idx]], [min_price], color="#3fb950", s=100, zorder=5, label=f"Mínimo")
    ax.annotate(
        f" Mín: ${min_price:,.0f}",
        xy=(dates[min_idx], min_price),
        color="#3fb950", fontsize=9, va="center"
    )

    ax.scatter([dates[max_idx]], [max_price], color="#f85149", s=100, zorder=5, label=f"Máximo")
    ax.annotate(
        f" Máx: ${max_price:,.0f}",
        xy=(dates[max_idx], max_price),
        color="#f85149", fontsize=9, va="center"
    )

    # ── Precio actual ──
    if current_price and dates:
        ax.scatter([dates[-1]], [current_price], color="#e3b341", s=120, zorder=5, marker="*")
        ax.annotate(
            f" Actual: ${current_price:,.0f}",
            xy=(dates[-1], current_price),
            color="#e3b341", fontsize=10, fontweight="bold", va="center"
        )

    # ── Línea de precio promedio ──
    avg_price = sum(prices) / len(prices)
    ax.axhline(y=avg_price, color="#8b949e", linewidth=1, linestyle="--", alpha=0.6)
    ax.text(
        dates[0], avg_price * 1.01,
        f"Promedio: ${avg_price:,.0f}",
        color="#8b949e", fontsize=8, alpha=0.8
    )

    # ── Formateo de ejes ──
    ax.yaxis.set_major_formatter(format_price_axis(currency))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %H:%M"))
    plt.xticks(rotation=30, ha="right", fontsize=8, color="#8b949e")
    plt.yticks(fontsize=9, color="#8b949e")

    # ── Grid sutil ──
    ax.grid(True, color="#21262d", linestyle="-", linewidth=0.8, alpha=0.8)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_edgecolor("#30363d")

    # ── Variación porcentual ──
    if len(prices) >= 2:
        pct_change = ((prices[-1] - prices[0]) / prices[0]) * 100
        change_color = "#3fb950" if pct_change <= 0 else "#f85149"
        change_arrow = "▼" if pct_change <= 0 else "▲"
        change_text = f"{change_arrow} {abs(pct_change):.1f}% vs inicio"
        fig.text(0.98, 0.02, change_text, ha="right", va="bottom",
                 color=change_color, fontsize=10, fontweight="bold",
                 transform=fig.transFigure)

    # ── Títulos ──
    store_display = store.upper()
    title = f"{product_name[:55]}{'...' if len(product_name) > 55 else ''}"
    ax.set_title(title, color="#e6edf3", fontsize=12, fontweight="bold", pad=15)
    ax.set_xlabel("Fecha / Hora", color="#8b949e", fontsize=9)
    ax.set_ylabel(f"Precio ({currency})", color="#8b949e", fontsize=9)

    # Subtítulo con tienda
    fig.text(0.5, 0.01, f"Fuente: {store_display} · {len(prices)} registros",
             ha="center", color="#8b949e", fontsize=8, transform=fig.transFigure)

    plt.tight_layout(rect=[0, 0.04, 1, 1])

    # ── Exportar a bytes ──
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=130, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close(fig)
    return buf.read()


def _generate_no_data_chart(product_name: str) -> bytes:
    """Genera una imagen de placeholder cuando no hay datos."""
    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(8, 4))
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#161b22")
    ax.text(0.5, 0.5, "📊 Sin datos suficientes aún\nVolvé más tarde",
            ha="center", va="center", color="#8b949e",
            fontsize=14, transform=ax.transAxes)
    ax.set_title(product_name[:60], color="#e6edf3", fontsize=11)
    ax.axis("off")
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    buf.seek(0)
    plt.close(fig)
    return buf.read()


def generate_summary_chart(products_data: list) -> bytes:
    """
    Genera un gráfico de resumen con la variación de todos los productos
    en las últimas 24h.
    """
    if not products_data:
        return _generate_no_data_chart("Resumen de productos")

    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(10, max(4, len(products_data) * 0.8)))
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#161b22")

    names = [p["name"][:30] for p in products_data]
    changes = [p.get("change_pct", 0) for p in products_data]
    colors = ["#3fb950" if c <= 0 else "#f85149" for c in changes]

    bars = ax.barh(names, changes, color=colors, edgecolor="#30363d", height=0.6)

    for bar, val in zip(bars, changes):
        ax.text(
            val + (0.1 if val >= 0 else -0.1),
            bar.get_y() + bar.get_height() / 2,
            f"{val:+.1f}%",
            va="center", ha="left" if val >= 0 else "right",
            color="white", fontsize=9
        )

    ax.axvline(x=0, color="#8b949e", linewidth=1)
    ax.set_xlabel("Variación %", color="#8b949e")
    ax.set_title("📊 Resumen de variaciones de precios", color="#e6edf3",
                 fontsize=13, fontweight="bold")
    ax.tick_params(colors="#8b949e")
    for spine in ax.spines.values():
        spine.set_edgecolor("#30363d")

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close(fig)
    return buf.read()
