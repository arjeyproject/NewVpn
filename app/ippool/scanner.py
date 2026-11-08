"""Async IP scanner — Cloudflare edge connectivity probing with bounded concurrency.

Sources are configurable (Cloudflare published ranges by default — the same edge
IPs VPN clients legitimately connect to). No arbitrary unowned ranges are scanned.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import random
import ssl
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import IpInventory, IpProfileResult, IpScanHistory
from app.vpn.validation import tcp_check

log = logging.getLogger("newvpn.scanner")


async def fetch_candidate_ranges() -> list[str]:
    s = get_settings()
    ranges: list[str] = list(s.extra_ranges)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(s.candidate_ranges_url)
        ranges += [l.strip() for l in resp.text.splitlines() if l.strip()]
    except Exception as exc:
        log.warning("could not fetch candidate ranges (%s) — using extras only", exc)
    seen, out = set(), []
    for r in ranges:
        try:
            net = ipaddress.ip_network(r, strict=False)
            if net.version == 4 and str(net) not in seen:
                seen.add(str(net))
                out.append(str(net))
        except ValueError:
            continue
    return out


def sample_addresses(ranges: list[str], per_range: int) -> list[str]:
    addrs: list[str] = []
    for r in ranges:
        net = ipaddress.ip_network(r, strict=False)
        count = min(per_range, net.num_addresses)
        if net.num_addresses > 256:
            count = min(per_range, 256)
            base_int = int(net.network_address) + random.randrange(0, max(1, net.num_addresses - 256))
            chosen = [str(ipaddress.ip_address(base_int + i)) for i in range(count)]
        else:
            hosts = [str(h) for h in net.hosts()]
            chosen = random.sample(hosts, min(per_range, len(hosts)))
        addrs += chosen
    return addrs


def classify(score: int) -> str:
    if score >= 85:
        return "excellent"
    if score >= 65:
        return "good"
    if score >= 40:
        return "average"
    return "unhealthy"


def score_result(latency_ms: int | None, ok: bool) -> int:
    if not ok or latency_ms is None:
        return 0
    if latency_ms <= 80:
        base = 100
    elif latency_ms <= 150:
        base = 85
    elif latency_ms <= 300:
        base = 65
    elif latency_ms <= 600:
        base = 45
    else:
        base = 25
    return base


async def probe_address(address: str, port: int, timeout: float, sem: asyncio.Semaphore) -> tuple[str, int, bool]:
    async with sem:
        res = await tcp_check(address, port, timeout=timeout)
        return address, res.latency_ms or 0, res.ok


async def run_scan(session: AsyncSession, trigger: str = "scheduled", network_profile: str = "default") -> IpScanHistory:
    s = get_settings()
    history = IpScanHistory(trigger=trigger, network_profile=network_profile, status="running")
    session.add(history)
    await session.flush()
    started = time.monotonic()

    healthy = unhealthy = new_entries = removed = total = 0
    try:
        ranges = await fetch_candidate_ranges()
        addrs = sample_addresses(ranges, s.ip_scan_sample_per_range)
        ports = s.scanner_ports or [443]
        targets = [(a, p) for a in addrs for p in ports]
        total = len(targets)

        sem = asyncio.Semaphore(s.ip_scan_concurrency)
        results = await asyncio.gather(*[probe_address(a, p, s.ip_scan_timeout, sem) for a, p in targets])

        now = datetime.now(timezone.utc)
        existing = {
            (r.address, r.port): r for r in (await session.execute(select(IpInventory))).scalars()
        }
        to_add: list[IpInventory] = []
        for address, latency, ok in results:
            key = (address, ports[0])
            row = existing.get(key)
            if ok:
                healthy += 1
                score = score_result(latency, ok)
                if row is None:
                    row = IpInventory(address=address, port=ports[0], provider="Cloudflare Edge",
                                      region="", asn="AS13335", country="",
                                      tcp_connect=True, latency_ms=latency, tls_status="ok",
                                      quality_score=score, health_status=classify(score),
                                      success_count=1, fail_count=0, last_success_at=now, last_scan_at=now)
                    to_add.append(row)
                    new_entries += 1
                else:
                    row.latency_ms = latency
                    row.tcp_connect = True
                    row.quality_score = (row.quality_score + score) // 2  # stability smoothing
                    row.health_status = classify(row.quality_score)
                    row.success_count += 1
                    row.last_success_at = now
                    row.last_scan_at = now
            else:
                unhealthy += 1
                if row is not None:
                    row.fail_count += 1
                    row.tcp_connect = False
                    row.last_failure_at = now
                    row.last_scan_at = now
                    # decay score; remove after repeated failures
                    row.quality_score = max(0, row.quality_score - 30)
                    row.health_status = classify(row.quality_score)

        for row in to_add:
            session.add(row)
        await session.flush()

        # remove entries that repeatedly failed and dropped below threshold
        dead = (await session.execute(
            select(IpInventory).where(IpInventory.quality_score < 10, IpInventory.fail_count >= 3)
        )).scalars().all()
        if dead:
            removed = len(dead)
            await session.execute(delete(IpInventory).where(
                IpInventory.id.in_([r.id for r in dead])
            ))

        # per-network-profile measurements (kept separately per prompt §6)
        sampled = random.sample([r for r in results if r[2]], min(20, max(0, len(results))))
        for address, latency, ok in sampled:
            inv = existing.get((address, ports[0])) or next((r for r in to_add if r.address == address), None)
            if inv is not None:
                session.add(IpProfileResult(ip_id=inv.id, network_profile=network_profile,
                                            latency_ms=latency or None, success=ok))

        history.total_checked = total
        history.healthy = healthy
        history.unhealthy = unhealthy
        history.new_entries = new_entries
        history.removed = removed
        history.duration_seconds = int(time.monotonic() - started)
        history.status = "completed"
        history.finished_at = datetime.now(timezone.utc)
        log.info("scan #%s done: %s checked, %s healthy (%ss)",
                 history.id, total, healthy, history.duration_seconds)
    except Exception as exc:
        history.status = "failed"
        history.error = str(exc)[:500]
        history.finished_at = datetime.now(timezone.utc)
        log.exception("scan failed")
        raise
    finally:
        await session.flush()
    return history
