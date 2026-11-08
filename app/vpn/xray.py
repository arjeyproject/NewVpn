"""Xray-core configuration management.

Builds the running config.json from active clients. REALITY keys and the
self-signed TLS certificate for Trojan are generated once and persisted in the
xray config directory (shared volume with the xray container).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings
from app.security.crypto import generate_short_ids, generate_x25519_keypair

log = logging.getLogger("newvpn.xray")

REALITY_DEFAULT_FINGERPRINT = "chrome"


class XrayState:
    """On-disk state shared with the xray container."""

    def __init__(self, config_dir: str | None = None):
        self.dir = Path(config_dir or get_settings().xray_config_dir)
        self.config_path = self.dir / "config.json"
        self.meta_path = self.dir / "reality.json"
        self.cert_path = self.dir / "trojan-cert.pem"
        self.key_path = self.dir / "trojan-key.pem"

    def ensure_dir(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)

    # ---------- reality keys / cert bootstrap ----------
    def ensure_reality_keys(self) -> dict:
        """Load or create REALITY keypair + short ids (persisted as JSON)."""
        if self.meta_path.exists():
            try:
                return json.loads(self.meta_path.read_text())
            except ValueError:
                pass
        priv, pub = generate_x25519_keypair()
        short_ids = generate_short_ids(2)
        meta = {"private_key": priv, "public_key": pub, "short_ids": short_ids, "created_at": datetime.now(timezone.utc).isoformat()}
        self.ensure_dir()
        tmp = self.meta_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(meta, indent=2))
        os.replace(tmp, self.meta_path)
        os.chmod(self.meta_path, 0o600)
        return meta

    def ensure_trojan_cert(self, hostname: str | None = None) -> None:
        """Generate a self-signed certificate for Trojan TLS when no domain cert exists."""
        if self.cert_path.exists() and self.key_path.exists():
            return
        self.ensure_dir()
        host = hostname or get_settings().reality_server_name
        # openssl-based generation (available in the bot container image)
        subprocess_run(
            "openssl req -x509 -newkey rsa:2048 -sha256 -days 825 -nodes "
            f'-subj "/CN={host}" -keyout {self.key_path} -out {self.cert_path}'
        )
        os.chmod(self.key_path, 0o600)

    # ---------- full config ----------
    def build_config(
        self,
        reality_clients: list[dict],   # [{id, email, flow}]
        ws_clients: list[dict],        # [{id, email}]
        trojan_tcp_clients: list[dict],  # [{password, email}]
        trojan_ws_clients: list[dict],
        chain_inbounds: list[dict] | None = None,  # per-profile proxy-chain inbounds
        chain_outbounds: list[dict] | None = None,  # upstream proxy outbounds
        routing_rules: list[dict] | None = None,
    ) -> dict:
        s = get_settings()
        meta = self.ensure_reality_keys()
        short_ids = meta["short_ids"]

        inbounds: list[dict] = []

        if reality_clients:
            inbounds.append({
                "tag": "in-reality",
                "listen": "0.0.0.0",
                "port": s.xray_reality_port,
                "protocol": "vless",
                "settings": {
                    "clients": [
                        {"id": c["id"], "email": c.get("email", f"c{i}"), "flow": c.get("flow", "xtls-rprx-vision")}
                        for i, c in enumerate(reality_clients)
                    ],
                    "decryption": "none",
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "show": False,
                        "dest": s.reality_dest,
                        "xver": 0,
                        "serverNames": [s.reality_server_name],
                        "privateKey": meta["private_key"],
                        "shortIds": short_ids,
                    },
                },
            })

        if ws_clients:
            base_path = f"{s.ws_path_prefix}/ws"
            inbounds.append({
                "tag": "in-ws",
                "listen": "0.0.0.0",
                "port": s.xray_ws_port,
                "protocol": "vless",
                "settings": {
                    "clients": [{"id": c["id"], "email": c.get("email", f"w{i}")} for i, c in enumerate(ws_clients)],
                    "decryption": "none",
                },
                "streamSettings": {
                    "network": "ws",
                    "security": "none",
                    "wsSettings": {"path": base_path},
                },
            })

        free_up = len(trojan_tcp_clients) > 0 or len(trojan_ws_clients) > 0
        if free_up:
            self.ensure_trojan_cert()
            if trojan_tcp_clients:
                inbounds.append({
                    "tag": "in-trojan-tls",
                    "listen": "0.0.0.0",
                    "port": s.xray_trojan_port,
                    "protocol": "trojan",
                    "settings": {
                        "clients": [
                            {"password": c["password"], "email": c.get("email", f"t{i}")}
                            for i, c in enumerate(trojan_tcp_clients)
                        ]
                    },
                    "streamSettings": {
                        "network": "tcp",
                        "security": "tls",
                        "tlsSettings": {"certificates": [{"certificateFile": str(self.cert_path), "keyFile": str(self.key_path)}]},
                    },
                })
            if trojan_ws_clients:
                inbounds.append({
                    "tag": "in-trojan-ws",
                    "listen": "0.0.0.0",
                    "port": s.xray_trojan_port + 1,
                    "protocol": "trojan",
                    "settings": {
                        "clients": [
                            {"password": c["password"], "email": c.get("email", f"tw{i}")}
                            for i, c in enumerate(trojan_ws_clients)
                        ]
                    },
                    "streamSettings": {
                        "network": "ws",
                        "security": "tls",
                        "tlsSettings": {"certificates": [{"certificateFile": str(self.cert_path), "keyFile": str(self.key_path)}]},
                        "wsSettings": {"path": f"{s.ws_path_prefix}/tws"},
                    },
                })

        for inb in (chain_inbounds or []):
            inbounds.append(inb)

        outbounds: list[dict] = [
            {"tag": "direct", "protocol": "freedom", "settings": {}},
            {"tag": "block", "protocol": "blackhole", "settings": {"response": {"type": "http"}}},
        ]
        outbounds += (chain_outbounds or [])

        rules: list[dict] = [
            {"inboundTag": ["in-ws", "in-reality", "in-trojan-tls", "in-trojan-ws"], "outboundTag": "direct", "type": "field"}
        ]
        rules += (routing_rules or [])
        # block private-range egress explicitly (no geoip.dat dependency)
        rules.append({
            "ip": ["127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
                   "169.254.0.0/16", "100.64.0.0/10", "::1/128", "fc00::/7"],
            "outboundTag": "block", "type": "field",
        })

        return {
            "log": {"loglevel": os.getenv("XRAY_LOGLEVEL", "warning")},
            "inbounds": inbounds,
            "outbounds": outbounds,
            "routing": {"domainStrategy": "AsIs", "rules": rules},
        }

    def write_config(self, config: dict) -> None:
        self.ensure_dir()
        tmp = self.config_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(config, indent=2))
        os.replace(tmp, self.config_path)

    def atomic_swap(self, config: dict) -> None:
        """Write config atomically; xray container restarts on file change by supervisor loop."""
        self.write_config(config)


def subprocess_run(cmd: str) -> None:
    proc = subprocess_run_async_sync(cmd)
    if proc.returncode != 0:
        raise RuntimeError(f"command failed: {cmd[:80]}…: {proc.stderr[-300:]}")


def subprocess_run_async_sync(cmd: str):
    import subprocess
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)


async def restart_xray() -> bool:
    """Ask the xray supervisor to reload; on the host compose stack, xray runs
    with a config-reloader loop so we just touch a marker file it watches."""
    marker = Path(get_settings().xray_config_dir) / ".reload"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(datetime.now(timezone.utc).isoformat())
    return True
