"""VLESS / Trojan share-link builders and parsers.

Link formats follow the de-facto client standard (v2rayNG, Nekobox, Streisand, ...):
- vless://uuid@host:port?type=ws&security=tls&sni=...&host=...&path=...#name
- trojan://password@host:port?security=tls&sni=...&type=ws&host=...&path=...&allowInsecure=1#name
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote, urlencode, urlparse, parse_qsl, unquote


@dataclass
class ConfigParams:
    protocol: str          # vless | trojan
    address: str
    port: int
    credential: str        # uuid or password
    transport: str = "tcp"           # ws | grpc | tcp
    security: str = "none"           # tls | reality | none
    sni: str | None = None
    host_header: str | None = None
    path: str | None = None
    service_name: str | None = None  # grpc
    flow: str | None = None          # xtls-rprx-vision
    fingerprint: str | None = None
    public_key: str | None = None    # reality pbk
    short_id: str | None = None      # reality sid
    spider_x: str | None = None
    allow_insecure: bool = False
    name: str = "config"


def build_vless_link(p: ConfigParams) -> str:
    q: list[tuple[str, str]] = [("type", p.transport)]
    if p.security == "reality":
        q += [("security", "reality"), ("encryption", "none")]
        if p.sni:
            q.append(("sni", p.sni))
        if p.flow:
            q.append(("flow", p.flow))
        if p.fingerprint:
            q.append(("fp", p.fingerprint))
        if p.public_key:
            q.append(("pbk", p.public_key))
        if p.short_id:
            q.append(("sid", p.short_id))
        if p.spider_x:
            q.append(("spx", quote(p.spider_x, safe="")))
    elif p.security == "tls":
        q += [("security", "tls"), ("encryption", "none")]
        if p.sni:
            q.append(("sni", p.sni))
        if p.fingerprint:
            q.append(("fp", p.fingerprint))
        if p.allow_insecure:
            q.append(("allowInsecure", "1"))
    else:
        q += [("security", "none"), ("encryption", "none")]
    if p.transport == "ws":
        if p.path:
            q.append(("path", p.path))
        if p.host_header:
            q.append(("host", p.host_header))
    elif p.transport == "grpc" and p.service_name:
        q += [("serviceName", p.service_name), ("mode", "gun")]
    return f"vless://{p.credential}@{p.address}:{p.port}?{urlencode(q)}#{quote(p.name, safe='')}"


def build_trojan_link(p: ConfigParams) -> str:
    q: list[tuple[str, str]] = [("type", p.transport), ("security", "tls")]
    if p.sni:
        q.append(("sni", p.sni))
    if p.allow_insecure:
        q.append(("allowInsecure", "1"))
    if p.fingerprint:
        q.append(("fp", p.fingerprint))
    if p.transport == "ws":
        if p.path:
            q.append(("path", p.path))
        if p.host_header:
            q.append(("host", p.host_header))
    return f"trojan://{quote(p.credential, safe='')}@{p.address}:{p.port}?{urlencode(q)}#{quote(p.name, safe='')}"


def build_link(p: ConfigParams) -> str:
    if p.protocol == "vless":
        return build_vless_link(p)
    if p.protocol == "trojan":
        return build_trojan_link(p)
    raise ValueError(f"unsupported protocol: {p.protocol}")


def parse_link(link: str) -> ConfigParams:
    """Parse a vless:// or trojan:// share link back into ConfigParams (round-trip safety)."""
    scheme = urlparse(link).scheme.lower()
    if scheme not in ("vless", "trojan"):
        raise ValueError(f"unsupported link scheme: {scheme}")
    rest = link[len(scheme) + 3:]
    fragment = ""
    if "#" in rest:
        rest, fragment = rest.split("#", 1)
    if "?" in rest:
        creds_host, query = rest.split("?", 1)
    else:
        creds_host, query = rest, ""
    credential, hostport = creds_host.rsplit("@", 1)
    host, port = hostport.rsplit(":", 1)
    params = dict(parse_qsl(query, keep_blank_values=True))
    return ConfigParams(
        protocol=scheme,
        address=host,
        port=int(port),
        credential=unquote(credential),
        transport=params.get("type", "tcp"),
        security=params.get("security", "none"),
        sni=params.get("sni"),
        host_header=params.get("host"),
        path=params.get("path"),
        service_name=params.get("serviceName"),
        flow=params.get("flow"),
        fingerprint=params.get("fp"),
        public_key=params.get("pbk"),
        short_id=params.get("sid"),
        spider_x=params.get("spx"),
        allow_insecure=params.get("allowInsecure") == "1",
        name=unquote(fragment),
    )
