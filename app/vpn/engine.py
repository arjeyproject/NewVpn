"""VPN provisioning engine — real generation + real validation, honest counts.

Endpoint inventory (no domain):        Endpoint inventory (user CF domain connected):
  1. VLESS+REALITY  server_ip:443        1-4. direct endpoints as left
  2. VLESS+WS       server_ip:8080       5. VLESS+WS via cleanIP:443 (CF front, TLS at edge)
  3. Trojan+TLS     server_ip:8443       6. Trojan+WS via cleanIP:443 (CF front)
  4. Trojan+WS      server_ip:8444

Each config gets its own credential (UUID/password). Endpoints that fail live
validation are NOT delivered — the actual healthy count is reported.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import utcnow, CloudflareAccount, CloudflareZone, Domain, IpInventory, VpnConfig, VpnProfile, Subscription, User
from app.security import crypto
from app.subscriptions.service import create_subscription
from app.vpn import links, validation, xray
from app.vpn.xray import REALITY_DEFAULT_FINGERPRINT, XrayState

log = logging.getLogger("newvpn.provisioning")


@dataclass
class ProvisionedConfig:
    db_id: int
    name: str
    link: str
    protocol: str
    transport: str
    address: str
    port: int
    check_class: str
    latency_ms: int | None
    detail: str


@dataclass
class ProvisionResult:
    profile_id: int
    subscription_token: str
    subscription_url: str
    configs: list[ProvisionedConfig]
    skipped: list[str]  # endpoints attempted but failed validation

    @property
    def count(self) -> int:
        return len(self.configs)


def _endpoint_specs(domain_name: str | None) -> list[dict]:
    """Distinct endpoint combinations — each entry is a genuinely different transport."""
    s = get_settings()
    specs = [
        {"protocol": "vless", "transport": "reality", "address": s.server_public_ip, "port": s.xray_reality_port,
         "sni": s.reality_server_name, "security": "reality", "tag": "in-reality"},
        {"protocol": "vless", "transport": "ws", "address": s.server_public_ip, "port": s.xray_ws_port,
         "path": f"{s.ws_path_prefix}/ws", "security": "none", "tag": "in-ws"},
        {"protocol": "trojan", "transport": "trojan-tls", "address": s.server_public_ip, "port": s.xray_trojan_port,
         "sni": s.reality_server_name, "security": "tls", "insecure": True, "tag": "in-trojan-tls"},
        {"protocol": "trojan", "transport": "trojan-ws", "address": s.server_public_ip, "port": s.xray_trojan_port + 1,
         "sni": s.reality_server_name, "path": f"{s.ws_path_prefix}/tws", "security": "tls", "insecure": True,
         "tag": "in-trojan-ws"},
    ]
    if domain_name:
        # CF-fronted entries are appended by the caller with real clean IPs from the pool.
        pass
    return specs


async def _clean_ips(session: AsyncSession, limit: int) -> list[IpInventory]:
    s = get_settings()
    rows = await session.execute(
        select(IpInventory)
        .where(IpInventory.health_status.in_(("excellent", "good")))
        .order_by(IpInventory.quality_score.desc())
        .limit(limit)
    )
    return list(rows.scalars())


async def provision_profile(
    session: AsyncSession,
    user: User,
    profile_name: str,
    protocol: str,           # vless | trojan | mixed
    domain: Domain | None,
    with_cf: bool,
    expiry_days: int | None = None,
) -> ProvisionResult:
    s = get_settings()
    state = XrayState()
    wanted = max(2, s.configs_per_profile)

    # Resolve user's CF zone domain (if connected & allowed)
    domain_name = domain.name if domain else None
    clean_ips = await _clean_ips(session, wanted) if (with_cf and domain_name) else []

    # Build candidate endpoint list (protocol-filtered, distinct)
    candidates: list[dict] = []
    for spec in _endpoint_specs(domain_name):
        if protocol != "mixed" and spec["protocol"] != protocol:
            continue
        candidates.append(dict(spec))
    # CF-fronted: one clean IP per entry, ws transport via CF edge TLS
    if clean_ips and domain_name:
        for ip in clean_ips[:2]:
            candidates.append({
                "protocol": "vless", "transport": "ws", "address": ip.address, "port": 443,
                "sni": domain_name, "host_header": domain_name, "path": f"{s.ws_path_prefix}/ws",
                "security": "tls", "tag": "in-ws", "proxied": True,
            })

    profile = VpnProfile(
        user_id=user.id, name=profile_name, protocol=protocol,
        domain_id=domain.id if domain else None,
        expires_at=None,
    )
    session.add(profile)
    await session.flush()

    # ---- Phase A: create tentative configs for every candidate ----
    tentative: list[tuple[dict, VpnConfig]] = []
    for i, spec in enumerate(candidates):
        cred = crypto.generate_uuid() if spec["protocol"] == "vless" else crypto.generate_trojan_password()
        email_tag = f"p{profile.id}-{spec['tag']}-{i}"
        cfg = VpnConfig(
            profile_id=profile.id,
            protocol=spec["protocol"], transport=spec["transport"],
            address=spec["address"], port=spec["port"],
            sni=spec.get("sni"), host_header=spec.get("host_header"), path=spec.get("path"),
            credential=cred, internal_tag=email_tag,
            fingerprint=REALITY_DEFAULT_FINGERPRINT,
            name=f"{profile_name} #{i + 1}",
            proxied_via_cf=bool(spec.get("proxied")),
        )
        if spec["tag"] == "in-reality":
            cfg.flow = "xtls-rprx-vision"
        session.add(cfg)
        tentative.append((spec, cfg))
    await session.flush()

    # ---- Phase B: write xray config INCLUDING new clients, reload, wait ----
    await _rebuild_xray(session, state)
    await asyncio.sleep(3.0)  # give the supervisor time to (re)bind ports

    # ---- Phase C: live validation of every candidate ----
    sem = asyncio.Semaphore(8)

    async def _check(spec: dict):
        async with sem:
            return await validation.validate_endpoint(
                spec["address"], spec["port"], spec["transport"], sni=spec.get("sni"),
                path=spec.get("path"), host_header=spec.get("host_header"),
            )

    results = await asyncio.gather(*[_check(c[0]) for c in tentative])
    checked = list(zip(tentative, results))

    provisioned: list[ProvisionedConfig] = []
    skipped: list[str] = []
    for (spec, cfg), res in checked:
        cfg.last_check_at = utcnow()
        if res.ok:
            cfg.status = "active"
            cfg.last_check_status = "ok"
            cfg.last_latency_ms = res.latency_ms
        else:
            cfg.status = "unhealthy"
            cfg.last_check_status = "fail"
            skipped.append(f"{spec['protocol']}+{spec['transport']} {spec['address']}:{spec['port']} — {res.detail}")
    await session.flush()

    # ---- Phase D: rebuild xray with healthy clients only ----
    await _rebuild_xray(session, state)

    # ---- Phase E: links + subscription for healthy configs ----
    for (spec, cfg), res in checked:
        if cfg.status != "active":
            continue
        params = links.ConfigParams(
            protocol=spec["protocol"], address=spec["address"], port=spec["port"], credential=cfg.credential,
            transport="ws" if "ws" in spec["transport"] else ("grpc" if spec["transport"] == "grpc" else "tcp"),
            security=spec.get("security", "none"), sni=spec.get("sni"),
            host_header=spec.get("host_header"), path=spec.get("path"),
            flow=cfg.flow, fingerprint=REALITY_DEFAULT_FINGERPRINT,
            allow_insecure=bool(spec.get("insecure")), name=cfg.name,
        )
        if spec["transport"] == "reality":
            meta = state.ensure_reality_keys()
            params.public_key = meta["public_key"]
            params.short_id = meta["short_ids"][0]
            params.flow = "xtls-rprx-vision"
            params.transport = "tcp"
        provisioned.append(ProvisionedConfig(
            db_id=cfg.id, name=cfg.name, link=links.build_link(params),
            protocol=spec["protocol"], transport=spec["transport"],
            address=spec["address"], port=spec["port"],
            check_class=res.check_class, latency_ms=res.latency_ms, detail=res.detail,
        ))

    sub = await create_subscription(session, profile)

    return ProvisionResult(
        profile_id=profile.id,
        subscription_token=sub.token,
        subscription_url=sub_url(sub.token),
        configs=provisioned,
        skipped=skipped,
    )


def sub_url(token: str) -> str:
    s = get_settings()
    base = s.subscription_base_url.rstrip("/") if s.subscription_base_url else f"http://{s.server_public_ip}:{s.sub_api_port}"
    return f"{base}/sub/{token}"


async def _rebuild_xray(session, state: XrayState) -> None:
    """Write xray config from every active config row and trigger a reload."""
    all_cfgs = (await session.execute(
        select(VpnConfig).where(VpnConfig.status == "active")
    )).scalars().all()
    rc, wc, tt, tw = [], [], [], []
    for c in all_cfgs:
        if c.protocol == "vless":
            entry = {"id": c.credential, "email": c.internal_tag or f"c{c.id}"}
            if c.transport == "reality":
                entry["flow"] = c.flow or "xtls-rprx-vision"
                rc.append(entry)
            elif c.transport == "ws":
                wc.append(entry)
        elif c.protocol == "trojan":
            entry = {"password": c.credential, "email": c.internal_tag or f"c{c.id}"}
            if c.transport == "trojan-tls":
                tt.append(entry)
            elif c.transport == "trojan-ws":
                tw.append(entry)
    state.atomic_swap(state.build_config(rc, wc, tt, tw))
    await xray.restart_xray()
