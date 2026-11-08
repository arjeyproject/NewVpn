"""Subscription management — secure tokens, rotation, revocation, expiry."""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Subscription, VpnConfig, VpnProfile
from app.security import crypto
from app.vpn import links


async def create_subscription(session: AsyncSession, profile: VpnProfile) -> Subscription:
    s = get_settings()
    expires = profile.expires_at or (datetime.now(timezone.utc) + timedelta(days=s.config_expiry_days))
    sub = Subscription(
        token=crypto.generate_subscription_token(),
        profile_id=profile.id,
        user_id=profile.user_id,
        expires_at=expires,
    )
    session.add(sub)
    await session.flush()
    return sub


async def rotate_token(session: AsyncSession, sub: Subscription) -> Subscription:
    old = sub.token
    sub.token = crypto.generate_subscription_token()
    sub.rotated_from = old
    sub.status = "active"
    await session.flush()
    return sub


async def revoke(session: AsyncSession, sub: Subscription) -> None:
    sub.status = "revoked"
    await session.flush()


async def get_active_by_token(session: AsyncSession, token: str) -> Subscription | None:
    row = await session.execute(select(Subscription).where(Subscription.token == token))
    sub = row.scalar_one_or_none()
    if sub is None:
        return None
    if sub.status != "active":
        return None
    if sub.expires_at and sub.expires_at < datetime.now(timezone.utc):
        sub.status = "expired"
        await session.flush()
        return None
    return sub


def config_to_link(cfg: VpnConfig) -> str:
    state = __import__("app.vpn.xray", fromlist=["XrayState"]).XrayState()
    params = links.ConfigParams(
        protocol=cfg.protocol, address=cfg.address, port=cfg.port, credential=cfg.credential,
        transport="ws" if "ws" in cfg.transport else "tcp",
        security="tls" if cfg.transport in ("trojan-tls", "trojan-ws") or cfg.proxied_via_cf else
                 ("reality" if cfg.transport == "reality" else "none"),
        sni=cfg.sni, host_header=cfg.host_header, path=cfg.path,
        flow=cfg.flow, fingerprint=cfg.fingerprint,
        allow_insecure=cfg.transport in ("trojan-tls", "trojan-ws"),
        name=cfg.name,
    )
    if cfg.transport == "reality":
        meta = state.ensure_reality_keys()
        params.public_key = meta["public_key"]
        params.short_id = meta["short_ids"][0]
    return links.build_link(params)


async def render_subscription_body(session: AsyncSession, sub: Subscription) -> tuple[str, dict]:
    """Return (base64 body, meta) — standard format accepted by mainstream clients."""
    rows = await session.execute(
        select(VpnConfig).where(
            VpnConfig.profile_id == sub.profile_id, VpnConfig.status == "active"
        ).order_by(VpnConfig.id)
    )
    cfgs = rows.scalars().all()
    lines = [config_to_link(c) for c in cfgs]
    body = base64.b64encode("\n".join(lines).encode()).decode()
    expire_ts = int(sub.expires_at.timestamp()) if sub.expires_at else 0
    meta = {
        "expire": expire_ts,
        "count": len(lines),
        "profile_name": (await session.get(VpnProfile, sub.profile_id)).name,
    }
    sub.last_accessed_at = datetime.now(timezone.utc)
    sub.access_count += 1
    await session.flush()
    return body, meta
