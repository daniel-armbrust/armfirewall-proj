from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from core import auth
from web.routes.dashboard import routes as dashboard_routes
from web.routes.firewall import routes as firewall_routes
from web.routes.interfaces import routes as interface_routes
from web.routes.login import routes as login_routes
from web.routes.menu import routes as menu_routes
from web.routes.monitoring import routes as monitoring_routes
from web.routes.network import routes as network_routes
from web.routes.settings import routes as settings_routes
from web.routes.services import routes as service_routes
from web.routes.tools import routes as tools_routes


ROOT_DIR = Path(__file__).resolve().parent
SUPERVISOR_CONF = ROOT_DIR / "conf" / "supervisord.conf"


def supervisor_program_installed(program_name: str) -> bool:
    """Return whether a supervisord program is registered."""
    if not SUPERVISOR_CONF.exists():
        return False
    return f"[program:{program_name}]" in SUPERVISOR_CONF.read_text(encoding="utf-8")

app = FastAPI(title="ArmFirewall")
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=6)
app.middleware("http")(auth.enforce_authentication)
app.mount("/static", StaticFiles(directory=ROOT_DIR / "web" / "static"), name="static")
app.mount("/rrd-img", StaticFiles(directory=ROOT_DIR / "rrd" / "img"), name="rrd_img")
app.state.menu_context = {
    "proxy_service_installed": supervisor_program_installed("armfirewall-squid"),
}

app.include_router(login_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(interface_routes.router)
app.include_router(network_routes.router)
app.include_router(firewall_routes.router)
app.include_router(monitoring_routes.router)
app.include_router(settings_routes.router)
app.include_router(service_routes.router)
app.include_router(tools_routes.router)
app.include_router(menu_routes.router)
