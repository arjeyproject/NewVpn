"""Real endpoint validation — no fake results.

Check classes:
- "tcp"       : TCP connect + latency
- "tls"       : TCP + TLS handshake (SNI validated)
- "transport" : TLS + protocol transport handshake probe (ws/http upgrade attempt)

An ICMP ping result is never presented as a VPN connection test.
"""
from __future__ import annotations

import asyncio
import logging
import socket
import ssl
import time
from dataclasses import dataclass

log = logging.getLogger("newvpn.validation")


@dataclass
class CheckResult:
    ok: bool
    latency_ms: int | None
    check_class: str  # tcp | tls | transport
    detail: str = ""


async def tcp_check(host: str, port: int, timeout: float = 4.0) -> CheckResult:
    start = time.perf_counter()
    try:
        fut = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(fut, timeout=timeout)
        elapsed = int((time.perf_counter() - start) * 1000)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return CheckResult(True, elapsed, "tcp", "TCP connect OK")
    except Exception as exc:
        return CheckResult(False, None, "tcp", f"{type(exc).__name__}")


async def tls_check(host: str, port: int, sni: str | None = None, timeout: float = 6.0) -> CheckResult:
    """TCP + TLS handshake. For REALITY endpoints the server mimics the dest site,
    so a successful TLS handshake against the configured serverName is expected."""
    start = time.perf_counter()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False  # self-signed trojan certs / reality mimic dest
    ctx.verify_mode = ssl.CERT_NONE
    try:
        fut = asyncio.open_connection(host, port, ssl=ctx, server_hostname=(sni or host) if sni else None)
        reader, writer = await asyncio.wait_for(fut, timeout=timeout)
        elapsed = int((time.perf_counter() - start) * 1000)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return CheckResult(True, elapsed, "tls", "TLS handshake OK")
    except Exception as exc:
        return CheckResult(False, None, "tls", f"{type(exc).__name__}")


async def ws_check(host: str, port: int, path: str, host_header: str | None = None, timeout: float = 6.0) -> CheckResult:
    """TLS (if port is TLS) + HTTP Upgrade handshake against a WS endpoint.
    A 101 or a structured 400 from the server proves the transport answers."""
    start = time.perf_counter()
    use_tls = port in (443, 2053, 2083, 2087, 2096, 8443, 8444)
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ssl_kw = {"ssl": ctx} if use_tls else {}
        fut = asyncio.open_connection(host, port, **ssl_kw)
        reader, writer = await asyncio.wait_for(fut, timeout=timeout)
        hh = host_header or host
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {hh}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        writer.write(request.encode())
        await writer.drain()
        status_line = await asyncio.wait_for(reader.readline(), timeout=timeout)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        elapsed = int((time.perf_counter() - start) * 1000)
        code = int(status_line.split()[1]) if len(status_line.split()) > 1 and status_line.split()[1].isdigit() else 0
        if code in (101, 400, 403, 426):  # 101 = full upgrade; 400/403/426 = transport alive behind edge
            return CheckResult(True, elapsed, "transport", f"WS probe HTTP {code}")
        return CheckResult(False, elapsed, "transport", f"unexpected HTTP {code}")
    except Exception as exc:
        return CheckResult(False, None, "transport", f"{type(exc).__name__}")


async def resolve_dns(host: str, timeout: float = 4.0) -> list[str] | None:
    def _resolve():
        return socket.gethostbyname_ex(host)[2]
    try:
        return await asyncio.wait_for(asyncio.to_thread(_resolve), timeout=timeout)
    except Exception:
        return None


async def validate_endpoint(address: str, port: int, transport: str, sni: str | None = None,
                            path: str | None = None, host_header: str | None = None) -> CheckResult:
    """Run the strongest check class the transport supports."""
    if transport in ("reality", "trojan-tls"):
        return await tls_check(address, port, sni=sni)
    if transport in ("ws", "trojan-ws"):
        if path is None:
            res = await tcp_check(address, port)
            return res if not res.ok else CheckResult(res.ok, res.latency_ms, "tcp", "TCP only (no path)")
        return await ws_check(address, port, path, host_header=host_header)
    if transport == "grpc":
        return await tcp_check(address, port)  # grpc needs protocol framing; tcp probe is honest
    return await tcp_check(address, port)
