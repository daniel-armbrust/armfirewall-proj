from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from core.constants import RRD_IMG_DIR

from web import auth
from web.constants import STATIC_DIR
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
from web.routes.workrequests import routes as workrequest_routes
from web.services.api import supervisor_program_exists


app = FastAPI(title="ArmFirewall")

app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=6)
app.middleware("http")(auth.enforce_authentication)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/rrd-img", StaticFiles(directory=RRD_IMG_DIR), name="rrd_img")

app.state.menu_context = {
    "proxy_service_installed": supervisor_program_exists("squid"),
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
app.include_router(workrequest_routes.router)
app.include_router(menu_routes.router)
