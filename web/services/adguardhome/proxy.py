"""Same-origin proxy for the locally bound AdGuard Home administration UI."""

from __future__ import annotations

from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import Response

from core.constants import ADGUARD_HOME_WEB_HOST, ADGUARD_HOME_WEB_PORT


ADGUARD_HOME_PROXY_PATH = "/services/adguard/ui"
HOP_BY_HOP_HEADERS = {
    "connection",
    "content-encoding",
    "content-length",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def upstream_url(path: str) -> str:
    """Build the local AdGuard Home URL for one proxied path."""
    suffix = path.lstrip("/")
    return f"http://{ADGUARD_HOME_WEB_HOST}:{ADGUARD_HOME_WEB_PORT}/{suffix}"


def proxied_location(location: str) -> str:
    """Keep AdGuard redirects inside the same-origin proxy path."""
    if location.startswith("/"):
        return f"{ADGUARD_HOME_PROXY_PATH}{location}"
    parsed = urlsplit(location)
    if parsed.hostname == ADGUARD_HOME_WEB_HOST and parsed.port == ADGUARD_HOME_WEB_PORT:
        suffix = parsed.path or "/"
        if parsed.query:
            suffix = f"{suffix}?{parsed.query}"
        return f"{ADGUARD_HOME_PROXY_PATH}{suffix}"
    return location


def proxied_cookie(value: str) -> str:
    """Scope AdGuard session cookies to the proxy path."""
    return value.replace("Path=/", f"Path={ADGUARD_HOME_PROXY_PATH}/")


async def proxy_adguardhome(request: Request, path: str = "") -> Response:
    """Proxy an authenticated request to the loopback-only AdGuard UI."""
    request_headers = {
        name: value
        for name, value in request.headers.items()
        if name.lower() not in HOP_BY_HOP_HEADERS | {"host", "accept-encoding"}
    }
    request_headers["host"] = f"{ADGUARD_HOME_WEB_HOST}:{ADGUARD_HOME_WEB_PORT}"
    request_headers["x-forwarded-host"] = request.headers.get("host", "")
    request_headers["x-forwarded-proto"] = request.url.scheme
    request_headers["x-forwarded-prefix"] = ADGUARD_HOME_PROXY_PATH

    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=30.0) as client:
            upstream = await client.request(
                request.method,
                upstream_url(path),
                params=request.query_params,
                content=await request.body(),
                headers=request_headers,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail="AdGuard Home is not available. Enable and start the service first.",
        ) from exc

    response_headers: dict[str, str] = {}
    set_cookies: list[str] = []
    for name, value in upstream.headers.multi_items():
        normalized = name.lower()
        if normalized in HOP_BY_HOP_HEADERS or normalized == "set-cookie":
            continue
        response_headers[name] = proxied_location(value) if normalized == "location" else value
    for value in upstream.headers.get_list("set-cookie"):
        set_cookies.append(proxied_cookie(value))

    response = Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
    )
    for cookie in set_cookies:
        response.headers.append("set-cookie", cookie)
    return response
