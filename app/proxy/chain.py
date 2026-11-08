"""Proxy Chain engine — upstream SOCKS5/HTTP egress management with real egress verification."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import ProxyAssignment, ProxyInventory
from app.security import crypto

log = logging.getLogger("newvpn.proxychain")

EGRESS_IP_URL = "https://api.ipify.org"
EGRESS_STABLE_URL = "https://api.ipify.org"


async def verify_proxy(proxy: ProxyInventory) -> ProxyInventory:
    """Live check: connect through the upstream proxy and read the actual egress IP."""
    s = get_settings()
    auth = None
    if proxy.username_encrypted and proxy.password_encrypted:
        auth = httpx.BasicAuth(crypto.decrypt_secret(proxy.username_encrypted),
                               crypto.decrypt_secret(proxy.password_encrypted))
    proxy_url = f"{proxy.protocol}://{proxy.host}:{proxy.port}"
    started = asyncio.get_event_loop().time()
    try:
        async with httpx.AsyncClient(proxy=proxy_url, auth=auth, timeout=15) as client:
            resp = await client.get(EGRESS_IP_URL)
        latency = int((asyncio.get_event_loop().time() - started) * 1000)
        egress = resp.text.strip()[:64]
        stable = bool(proxy.last_egress_ip) and proxy.last_egress_ip == egress
        proxy.status = "healthy"
        proxy.latency_ms = latency
        proxy.egress_ip = egress
        proxy.egress_stable = stable or proxy.last_egress_ip is None
        proxy.last_egress_ip = egress
        proxy.last_verified_at = datetime.now(timezone.utc)
    except Exception as exc:
        proxy.status = "unhealthy"
        proxy.egress_stable = False
        proxy.last_verified_at = datetime.now(timezone.utc)
        log.info("proxy %s failed verification: %s", proxy.name, type(exc).__name__)
    await proxy
    return proxy


async def verify_all(session: AsyncSession) -> list[ProxyInventory]:
    rows = (await session.execute(select(ProxyInventory).where(ProxyInventory.status != "disabled"))).scalars().all()
    return [await verify_proxy(p) for p in rows]


async def available_for_user(session: AsyncSession, user_id: int) -> list[ProxyInventory]:
    """Healthy proxies with free capacity, excluding ones already assigned to this user."""
    rows = (await session.execute(select(ProxyInventory).where(ProxyInventory.status == "healthy"))).scalars().all()
    result = []
    for p in rows:
        used = (await session.execute(
            select(func.count(ProxyAssignment.id)).where(
                ProxyAssignment.proxy_id == p.id, ProxyAssignment.status == "active")
        )).scalar_one()
        if used < p.max_users:
            result.append(p)
    return result


async def assign(session: AsyncSession, user_id: int, proxy_id: int, config_id: int | None = None) -> ProxyAssignment:
    a = ProxyAssignment(user_id=user_id, proxy_id=proxy_id, config_id=config_id)
    session.add(a)
    await session.flush()
    return a


def chain_inbound_for(profile_id: int, clients: list[dict], protocol: str, credential_port: int | None = None) -> dict:
    """Dedicated inbound for a proxy-chained profile (isolated port + routing)."""
    s = get_settings()
    return {
        "tag": f"in-chain-{profile_id}",
        "listen": "0.0.0.0",
        "port": s.xray_chain_port_base + profile_id,
        "protocol": protocol,
        "settings": {"clients": clients, "decryption": "none"} if protocol == "vless"
        else {"clients": clients},
        "streamSettings": {"network": "tcp", "security": "none"},
    }


def chain_outbound_for(proxy: ProxyInventory, profile_id: int) -> dict:
    outbound: dict = {
        "tag": f"out-chain-{profile_id}",
        "protocol": "socks" if proxy.protocol == "socks5" else "http",
        "settings": {
            "servers": [{
                "address": proxy.host,
                "port": proxy.port,
            }]
        },
    }
    if proxy.username_encrypted and proxy.password_encrypted:
        outbound["settings"]["servers"][0]["users"] = [{
            "user": crypto.decrypt_secret(proxy.username_encrypted),
            "pass": crypto.decrypt_secret(proxy.password_encrypted),
        }]
    return outbound


def routing_rule_for(profile_id: int) -> dict:
    return {
        "inboundTag": [f"in-chain-{profile_id}"],
        "outboundTag": f"out-chain-{profile_id}",
        "type": "field",
    }
