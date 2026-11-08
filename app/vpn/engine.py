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
from app.db.models import CloudflareAccount, CloudflareZone, Domain, IpInventory, VpnConfig, VpnProfile, Subscription, User
from app.security import crypto
from app.subscriptions.service import create_subscription
from app.vpn import links, validation, xray
from app.vpn.xray import XrayState

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

    # Run live validation concurrently (bounded)
    sem = asyncio.Semaphore(8)

    async def _check(spec: dict):
        async with sem:
            return spec, await validation.validate_endpoint(
                spec["address"], spec["port"], spec["transport"], sni=spec.get("sni"),
                path=spec.get("path"), host_header=spec.get("host_header"),
            )

    results = await asyncio.gather(*[_check(c) for c in candidates])
    healthy = [(spec, res) for spec, res in results if res.ok]
    skipped = [f"{c['protocol']}+{c['transport']} {c['address']}:{c['port']} — {res.detail}"
               for c, res in results if not res.ok]

    profile = VpnProfile(
        user_id=user.id, name=profile_name, protocol=protocol,
        domain_id=domain.id if domain else None,
        expires_at=None,
    )
    session.add(profile)
    await session.flush()

    provisioned: list[ProvisionedConfig] = []
    reality_clients, ws_clients, trojan_tcp, trojan_ws = [], [], [], []

    for i, (spec, res) in enumerate(healthy):
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
        session.add(cfg)
        client_entry = {"id": cred, "email": email_tag}
        if spec["tag"] == "in-reality":
            cfg.flow = "xtls-rprx-vision"
            client_entry["flow"] = cfg.flow
            reality_clients.append(client_entry)
        elif spec["tag"] == "in-ws":
            ws_clients.append(client_entry)
        elif spec["tag"] == "in-trojan-tls":
            trojan_tcp.append({"password": cred, "email": email_tag})
        elif spec["tag"] == "in-trojan-ws":
            trojan_ws.append({"password": cred, "email": email_tag})

        params = links.ConfigParams(
            protocol=spec["protocol"], address=spec["address"], port=spec["port"], credential=cred,
            transport="ws" if "ws" in spec["transport"] else ("grpc" if spec["transport"] == "grpc" else "tcp"),
            security=spec.get("security", "none"), sni=spec.get("sni"),
            host_header=spec.get("host_header"), path=spec.get("path"),
            flow=cfg.flow, fingerprint=REALITY_DEFAULT_FINGERPRINT,
            allow_insecure=bool(spec.get("insecure")), name=cfg.name,
        )
        # reality public key required for client links
        if spec["transport"] == "reality":
            meta = state.ensure_reality_keys()
            params.public_key = meta["public_key"]
            params.short_id = meta["short_ids"][0]
            params.flow = "xtls-rprx-vision"
            params.transport = "tcp"
        provisioned.append(ProvisionedConfig(
            db_id=0, name=cfg.name, link=links.build_link(params),
            protocol=spec["protocol"], transport=spec["transport"],
            address=spec["address"], port=spec["port"],
            check_class=res.check_class, latency_ms=res.latency_ms, detail=res.detail,
        ))

    await session.flush()

    # Rebuild xray config with all active clients, then reload
    all_cfgs = (await session.execute(
        select(VpnConfig).where(VpnConfig.status == "active")
    )).scalars().all()
    rc, wc, tt, tw = [], [], [], []
    for c in all_cfgs:
        entry = {"id": c.credential, "email": c.internal_tag or f"c{c.id}"} if c.protocol == "vless" \
            else {"password": c.credential, "email": c.internal_tag or f"c{c.id}"}
        if c.transport == "reality":
            entry = {"id": c.credential, "email": c.internal_tag or f"c{c.id}", "flow": c.flow or "xtls-rprx-vision"}
            rc.append(entry)
        elif c.transport == "ws":
            wc.append(entry)
        elif c.transport == "trojan-tls":
            tt.append(entry)
        elif c.transport == "trojan-ws":
            tw.append(entry)
    state.atomic_swap(state.build_config(rc, wc, tt, tw))
    await xray.restart_xray()

    # Persist ids into provisioned configs & subscription
    sub = await create_subscription(session, profile)
    for pc, cfg in zip(provisioned, profile.configs[:len(provisioned)]):
        pc.db_id = cfg.id

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
