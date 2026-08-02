from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from core.constants import RRD_IMG_DIR

from web import auth
from web.constants import STATIC_DIR
from web.adam import routes as adam_routes
from web.adam.datasets import routes as adam_datasets_routes
from web.adam.text_classification import routes as text_classification_training_routes
from web.adam.playground import routes as adam_playground_routes
from web.adam.transcription import routes as adam_transcription_routes
from web.adam.wake_word import routes as adam_wake_word_routes
from web.dashboard import routes as dashboard_routes
from web.firewall import routes as firewall_routes
from web.interfaces import routes as interface_routes
from web.login import routes as login_routes
from web.menu import routes as menu_routes
from web.monitoring import routes as monitoring_routes
from web.network import routes as network_routes
from web.services import routes as service_routes
from web.settings import routes as settings_routes
from web.tools import routes as tools_routes
from web.workrequests import routes as workrequest_routes
from web.services.api import service_installed


app = FastAPI(title="ArmFirewall")

app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=6)
app.middleware("http")(auth.enforce_authentication)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/rrd-img", StaticFiles(directory=RRD_IMG_DIR), name="rrd_img")

app.state.service_installed = service_installed

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
app.include_router(adam_routes.router)
app.include_router(adam_datasets_routes.router)
app.include_router(text_classification_training_routes.router)
app.include_router(adam_playground_routes.router)
app.include_router(adam_transcription_routes.router)
app.include_router(adam_wake_word_routes.router)
app.include_router(menu_routes.router)
