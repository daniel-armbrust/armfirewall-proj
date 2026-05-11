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


ROOT_DIR = Path(__file__).resolve().parent

app = FastAPI(title="ArmFirewall")
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=6)
app.middleware("http")(auth.enforce_authentication)
app.mount("/static", StaticFiles(directory=ROOT_DIR / "web" / "static"), name="static")
app.mount("/rrd-img", StaticFiles(directory=ROOT_DIR / "rrd" / "img"), name="rrd_img")

app.include_router(login_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(interface_routes.router)
app.include_router(network_routes.router)
app.include_router(firewall_routes.router)
app.include_router(monitoring_routes.router)
app.include_router(settings_routes.router)
app.include_router(service_routes.router)
app.include_router(menu_routes.router)
