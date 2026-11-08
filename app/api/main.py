"""Subscription HTTP API (aiohttp) — /sub/<token>, QR codes, health.

- No DB ids in URLs; only opaque tokens.
- Basic per-token rate limiting.
- subscription-userinfo header for client quota/expiry display.
"""
from __future__ import annotations

import asyncio
import io
import logging
import time

from aiohttp import web
from sqlalchemy import select

from app.config import get_settings
from app.db.engine import SessionFactory
from app.db.models import Subscription, VpnProfile
from app.subscriptions.service import get_active_by_token, render_subscription_body
from app.utils.qrcode import make_qr_png

log = logging.getLogger("newvpn.api")

_rate: dict[str, list[float]] = {}


def _rate_ok(token: str, limit: int) -> bool:
    now = time.monotonic()
    window = _rate.setdefault(token, [])
    window[:] = [t for t in window if now - t < 60]
    if len(window) >= limit:
        return False
    window.append(now)
    return True


async def handle_sub(request: web.Request) -> web.Response:
    token = request.match_info["token"]
    s = get_settings()
    if not _rate_ok(token, s.sub_request_rate_limit):
        return web.json_response({"error": "rate limit exceeded"}, status=429)
    async with SessionFactory() as session:
        sub = await get_active_by_token(session, token)
        if sub is None:
            return web.Response(text="subscription not found or expired", status=404)
        body, meta = await render_subscription_body(session, sub)
        profile = await session.get(VpnProfile, sub.profile_id)
        display_name = profile.name if profile else "NewVpn"
    resp = web.Response(text=body)
    resp.headers["Content-Type"] = "text/plain; charset=utf-8"
    resp.headers["subscription-userinfo"] = f"upload=0; download=0; total=0; expire={meta['expire']}"
    resp.headers["profile-title"] = display_name[:64]
    resp.headers["profile-update-interval"] = "6"
    return resp


async def handle_sub_qr(request: web.Request) -> web.Response:
    token = request.match_info["token"]
    async with SessionFactory() as session:
        sub = await get_active_by_token(session, token)
        if sub is None:
            return web.Response(status=404)
        body, _ = await render_subscription_body(session, sub)
    import base64
    try:
        links_raw = base64.b64decode(body).decode()
    except Exception:
        return web.Response(status=500)
    first = links_raw.splitlines()[0] if links_raw else ""
    png = make_qr_png(first)
    return web.Response(body=png, content_type="image/png")


async def handle_health(request: web.Request) -> web.Response:
    from app.db.engine import engine
    db_ok = False
    try:
        async with SessionFactory() as session:
            await session.execute(select(Subscription).limit(1))
        db_ok = True
    except Exception as exc:
        log.warning("health db check failed: %s", type(exc).__name__)
    s = get_settings()
    bot_configured = bool(s.bot_token)
    return web.json_response({
        "status": "ok" if db_ok else "degraded",
        "db": db_ok,
        "bot_configured": bot_configured,
        "version": "1.0.0",
    })


def build_app() -> web.Application:
    app = web.Application(client_max_size=1_000_000)
    app.router.add_get("/sub/{token}", handle_sub)
    app.router.add_get("/sub/{token}/qr", handle_sub_qr)
    app.router.add_get("/health", handle_health)
    return app


def run() -> None:
    s = get_settings()
    web.run_app(build_app(), host=s.sub_api_host, port=s.sub_api_port, print=None)
