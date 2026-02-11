"""
server.py - Servidor HTTP mínimo para mantener el servicio vivo en Render free tier.
Corre en un thread separado junto al bot de Telegram.
UptimeRobot lo pingea cada 14 minutos → Render nunca duerme el proceso.
"""

import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime

import database as db

PORT = int(os.getenv("PORT", 8080))


class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/":
            self._respond_health()
        elif self.path == "/status":
            self._respond_status()
        else:
            self.send_response(404)
            self.end_headers()

    def _respond_health(self):
        """Endpoint raíz — lo usa UptimeRobot para el ping."""
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

    def _respond_status(self):
        """Endpoint de estado — muestra productos y último chequeo."""
        try:
            products = db.get_active_products()
            lines = [f"🤖 Monitor de Precios — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"]
            lines.append(f"Productos monitoreados: {len(products)}\n\n")
            for p in products:
                last = db.get_last_price(p["id"])
                if last and last["price"]:
                    price_str = f"{last['currency']} {last['price']:,.0f}"
                    stock = "✅" if last["in_stock"] else "❌"
                    lines.append(f"{stock} [{p['store']}] {p['name'][:40]} — {price_str}\n")
                else:
                    lines.append(f"⏳ [{p['store']}] {p['name'][:40]} — sin datos\n")

            body = "".join(lines).encode()
        except Exception as e:
            body = f"Error: {e}".encode()

        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Silenciar logs de cada ping para no ensuciar la consola
        if self.path != "/":
            print(f"[HTTP] {self.address_string()} {format % args}")


def start_server():
    """Arranca el servidor HTTP en un thread daemon."""
    httpd = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    print(f"🌐 Servidor keep-alive escuchando en puerto {PORT}")
    print(f"   → GET /        (ping de UptimeRobot)")
    print(f"   → GET /status  (estado de productos)")
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd
