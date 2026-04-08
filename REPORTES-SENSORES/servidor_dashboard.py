# ============================================================
# servidor_dashboard.py — Servidor web privado para el dashboard
# ============================================================

import asyncio
import secrets
import os
import time
import socket
import logging
from aiohttp import web

log = logging.getLogger(__name__)

RUTA_HTML = os.path.join("recursos", "dashboard.html")
TOKEN_EXPIRACION = 600   # 10 minutos

# ⚠️ Cambia esto por tu URL de ngrok (la que aparece en "Forwarding")
DOMINIO_PUBLICO = "https://nonmutually-feisty-eilene.ngrok-free.dev"


def _obtener_ip_local() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class ServidorDashboard:

    def __init__(self, puerto: int = 8765, ip: str | None = None):
        self.puerto  = puerto
        self.ip      = ip or _obtener_ip_local()
        self._tokens: dict[str, float] = {}
        self._runner  = None
        self._site    = None

    # Gestión de tokens

    def generar_token(self) -> str:
        self._limpiar_tokens_expirados()
        token = secrets.token_urlsafe(32)
        self._tokens[token] = time.time()
        log.info(f"[Dashboard] Token generado — expira en {TOKEN_EXPIRACION//60} min")
        return token

    def _limpiar_tokens_expirados(self):
        ahora     = time.time()
        expirados = [t for t, ts in self._tokens.items()
                     if ahora - ts > TOKEN_EXPIRACION]
        for t in expirados:
            del self._tokens[t]

    def _validar_y_consumir_token(self, token: str) -> bool:
        self._limpiar_tokens_expirados()
        if token in self._tokens:
            log.info("[Dashboard] Token consumido — acceso concedido")
            return True
        log.warning("[Dashboard] Token inválido o expirado — acceso denegado")
        return False

    # URL pública

    def url_con_token(self, token: str) -> str:
        # Usa el dominio público de ngrok en lugar de la IP local
        return f"{DOMINIO_PUBLICO}/dashboard?token={token}"

    # Handler del dashboard

    async def _handle_dashboard(self, request: web.Request) -> web.Response:
        token = request.rel_url.query.get("token", "")

        if not token or not self._validar_y_consumir_token(token):
            return web.Response(
                status=403,
                content_type="text/html",
                text=(
                    "<!DOCTYPE html><html><head>"
                    "<meta charset='UTF-8'>"
                    "<title>Acceso denegado</title>"
                    "<style>body{background:#0a0a0f;color:#e2e4e9;"
                    "font-family:sans-serif;display:flex;align-items:center;"
                    "justify-content:center;height:100vh;text-align:center;}"
                    "h2{color:#ef4444;} p{color:#6b7280;margin-top:.5rem;}</style>"
                    "</head><body>"
                    "<div><h2>🔒 Acceso denegado</h2>"
                    "<p>El enlace ha expirado.<br>"
                    "Por favor solicite uno nuevo con el comando /dashboard en Telegram.</p>"
                    "</div></body></html>"
                ),
            )

        if not os.path.isfile(RUTA_HTML):
            return web.Response(
                status=500,
                content_type="text/plain",
                text="Error: no se encontró recursos/dashboard.html",
            )

        with open(RUTA_HTML, encoding="utf-8") as f:
            html = f.read()

        # Reemplaza localhost:3000 por la ruta /grafana del mismo túnel ngrok
        html = html.replace("http://localhost:3000", "/grafana")

        return web.Response(status=200, content_type="text/html", text=html)

    # Proxy de Grafana — evita necesitar un segundo túnel ngrok

    async def _handle_grafana(self, request: web.Request) -> web.StreamResponse:
        import aiohttp

        path = request.match_info.get("path", "")

        url = f"http://localhost:3000/grafana/{path}"

        if request.query_string:
            url += f"?{request.query_string}"

        try:

            headers = dict(request.headers)

            headers["Host"] = "localhost:3000"
            headers["X-Forwarded-Host"] = "nonmutually-feisty-eilene.ngrok-free.dev"
            headers["X-Forwarded-Proto"] = "https"
            headers["ngrok-skip-browser-warning"] = "true"

            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method=request.method,
                    url=url,
                    headers=headers,
                    data=await request.read(),
                    allow_redirects=False,
                ) as resp:
                    body = await resp.read()
                    response = web.Response(
                        body=body,
                        status=resp.status
                    )
                    for key, value in resp.headers.items():
                        if key.lower() not in (
                            "content-encoding",
                            "transfer-encoding",
                            "connection"
                        ):
                            response.headers[key] = value
                    return response

        except Exception as e:
            log.error(f"[Grafana proxy] Error: {e}")
            return web.Response(status=502, text="Error al conectar con Grafana")

    async def _handle_favicon(self, _request: web.Request) -> web.Response:
        return web.Response(status=204)

    # Ciclo de vida del servidor

    async def iniciar(self):
        app_web = web.Application()
        app_web.router.add_get("/dashboard",         self._handle_dashboard)
        app_web.router.add_route("*", "/grafana/{path:.*}", self._handle_grafana)
        app_web.router.add_get("/favicon.ico",       self._handle_favicon)

        self._runner = web.AppRunner(app_web, access_log=None)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "0.0.0.0", self.puerto)
        await self._site.start()
        log.info(f"[Dashboard] Servidor iniciado → {DOMINIO_PUBLICO}/dashboard")

    async def detener(self):
        if self._runner:
            await self._runner.cleanup()
            log.info("[Dashboard] Servidor detenido")
