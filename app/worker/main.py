"""Background worker — scheduler with PG job-locking, 8 jobs, admin alerts.

Jobs:
1. ip_scan              — twice daily (cron)
2. proxy_health         — every 10 min
3. endpoint_monitor     — every 5 min
4. sub_expiry           — every 30 min
5. cleanup              — daily
6. backup               — daily at BACKUP_SCHEDULE_HOUR
7. cf_verify            — daily
8. metrics              — every 5 min (monitor snapshots)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import delete, func, select, update

from app.config import get_settings
from app.db.engine import SessionFactory
from app.db.models import (BackgroundJob, CloudflareAccount, IpInventory, MonitorSnapshot,
                           ProxyAssignment, ProxyInventory, Subscription, User, VpnConfig, VpnProfile)

log = logging.getLogger("newvpn.worker")


async def _lock_job(name: str) -> BackgroundJob | None:
    """Insert a running job row; refuse when one is already running (duplicate prevention)."""
    async with SessionFactory() as session:
        running = (await session.execute(
            select(BackgroundJob).where(BackgroundJob.name == name, BackgroundJob.status == "running")
        )).scalar_one_or_none()
        if running is not None:
            # stale lock older than 2h is reclaimed
            if running.started_at and datetime.now(timezone.utc) - running.started_at < timedelta(hours=2):
                return None
            running.status = "failed"
            running.error = "reclaimed stale lock"
            running.finished_at = datetime.now(timezone.utc)
        job = BackgroundJob(name=name, status="running")
        session.add(job)
        await session.commit()
        return job


async def _finish_job(job: BackgroundJob, error: str | None = None) -> None:
    async with SessionFactory() as session:
        merged = await session.merge(job)
        merged.status = "failed" if error else "completed"
        merged.error = error[:500] if error else None
        merged.finished_at = datetime.now(timezone.utc)
        await session.commit()
        if error:
            await _alert(f"Job {job.name} failed: {error[:200]}")


_alert_state: dict[str, float] = {}


async def _alert(text: str) -> None:
    """Send admin alert with cooldown dedupe (never blocks on Telegram errors)."""
    import time
    key = text[:48]
    if time.monotonic() - _alert_state.get(key, 0) < get_settings().alert_cooldown_minutes * 60:
        return
    _alert_state[key] = time.monotonic()
    s = get_settings()
    if not s.bot_token:
        log.warning("ALERT (no bot token): %s", text)
        return
    try:
        from aiogram import Bot
        from aiogram.client.default import DefaultBotProperties
        bot = Bot(token=s.bot_token, default=DefaultBotProperties(parse_mode="HTML"))
        for admin_id in s.admin_ids:
            try:
                await bot.send_message(admin_id, f"🚨 <b>NewVpn alert</b>\n\n{text[:1000]}")
            except Exception:
                pass
        await bot.session.close()
    except Exception as exc:
        log.warning("alert delivery failed: %s", type(exc).__name__)


# ---------------- jobs ----------------

async def job_ip_scan(trigger: str = "scheduled") -> None:
    from app.ippool.scanner import run_scan
    job = await _lock_job("ip_scan")
    if job is None:
        log.info("ip_scan skipped — already running")
        return
    try:
        async with SessionFactory() as session:
            await run_scan(session, trigger=trigger)
            await session.commit()
    except Exception as exc:
        await _finish_job(job, error=str(exc))
        return
    await _finish_job(job)


async def enqueue_ip_scan(trigger: str = "manual") -> bool:
    """Schedule a one-off scan without blocking the caller (admin panel)."""
    job = await _lock_job("ip_scan")
    if job is None:
        return False
    await _finish_job(job)  # release; actual run happens on the scheduler
    asyncio.get_running_loop().create_task(_run_scan_task(trigger))
    return True


async def _run_scan_task(trigger: str) -> None:
    await asyncio.sleep(0.1)
    await job_ip_scan(trigger=trigger)


async def job_proxy_health() -> None:
    job = await _lock_job("proxy_health")
    if job is None:
        return
    try:
        from app.proxy.chain import verify_all
        async with SessionFactory() as session:
            await verify_all(session)
            await session.commit()
    except Exception as exc:
        await _finish_job(job, error=str(exc))
        return
    await _finish_job(job)


async def job_endpoint_monitor() -> None:
    job = await _lock_job("endpoint_monitor")
    if job is None:
        return
    try:
        from app.vpn import validation
        async with SessionFactory() as session:
            cfgs = (await session.execute(
                select(VpnConfig).where(VpnConfig.status == "active").limit(30))).scalars().all()
            down = []
            for c in cfgs:
                res = await validation.tcp_check(c.address, c.port, timeout=4.0)
                c.last_check_at = datetime.now(timezone.utc)
                c.last_check_status = "ok" if res.ok else "fail"
                c.last_latency_ms = res.latency_ms
                if not res.ok:
                    down.append(c.name)
                await session.merge(c)
            await session.commit()
        if down:
            await _alert("Endpoints down: " + ", ".join(down[:5]))
    except Exception as exc:
        await _finish_job(job, error=str(exc))
        return
    await _finish_job(job)


async def job_sub_expiry() -> None:
    job = await _lock_job("sub_expiry")
    if job is None:
        return
    try:
        now = datetime.now(timezone.utc)
        async with SessionFactory() as session:
            for model in (Subscription, VpnProfile, VpnConfig):
                rows = (await session.execute(
                    select(model).where(model.expires_at.is_not(None),
                                        model.expires_at < now,
                                        model.status == "active"))).scalars().all()
                for r in rows:
                    r.status = "expired"
            await session.commit()
    except Exception as exc:
        await _finish_job(job, error=str(exc))
        return
    await _finish_job(job)


async def job_cleanup() -> None:
    job = await _lock_job("cleanup")
    if job is None:
        return
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        async with SessionFactory() as session:
            await session.execute(delete(BackgroundJob).where(
                BackgroundJob.finished_at.is_not(None), BackgroundJob.finished_at < cutoff))
            await session.execute(delete(MonitorSnapshot).where(
                MonitorSnapshot.recorded_at < cutoff))
            await session.commit()
    except Exception as exc:
        await _finish_job(job, error=str(exc))
        return
    await _finish_job(job)


async def job_cf_verify() -> None:
    job = await _lock_job("cf_verify")
    if job is None:
        return
    try:
        from app.cloudflare.client import CloudflareClient
        from app.security import crypto
        async with SessionFactory() as session:
            accounts = (await session.execute(
                select(CloudflareAccount).where(CloudflareAccount.status == "active"))).scalars().all()
            for acc in accounts:
                try:
                    client = CloudflareClient(crypto.decrypt_secret(acc.api_token_encrypted))
                    info = await client.verify_token()
                    acc.status = "active" if info.valid else "invalid"
                except Exception:
                    acc.status = "invalid"
                    await _alert(f"Cloudflare account {acc.id} token invalid — user should reconnect.")
                acc.last_check_at = datetime.now(timezone.utc)
            await session.commit()
    except Exception as exc:
        await _finish_job(job, error=str(exc))
        return
    await _finish_job(job)


async def job_metrics() -> None:
    job = await _lock_job("metrics")
    if job is None:
        return
    try:
        import os
        async with SessionFactory() as session:
            cpu = os.getloadavg()[0] * 100 / max(1, os.cpu_count() or 1)
            try:
                with open("/proc/meminfo") as f:
                    info = dict(line.split(": ") for line in f if ": " in line)
                mem_total = int(info["MemTotal"].split()[0])
                mem_avail = int(info["MemAvailable"].split()[0])
                mem = 100 * (1 - mem_avail / mem_total)
                st = os.statvfs("/")
                disk = 100 * (1 - st.f_bavail / st.f_blocks)
            except Exception:
                mem = disk = 0
            users_total = (await session.execute(select(func.count(User.id)))).scalar_one()
            configs_active = (await session.execute(
                select(func.count(VpnConfig.id)).where(VpnConfig.status == "active"))).scalar_one()
            subs_active = (await session.execute(
                select(func.count(Subscription.id)).where(Subscription.status == "active"))).scalar_one()
            ips_healthy = (await session.execute(
                select(func.count(IpInventory.id)).where(
                    IpInventory.health_status.in_(("excellent", "good"))))).scalar_one()
            proxies_healthy = (await session.execute(
                select(func.count(ProxyInventory.id)).where(ProxyInventory.status == "healthy"))).scalar_one()
            session.add(MonitorSnapshot(cpu_percent=round(cpu, 1), mem_percent=round(mem, 1),
                                        disk_percent=round(disk, 1), users_total=users_total,
                                        configs_active=configs_active, subs_active=subs_active,
                                        ips_healthy=ips_healthy, proxies_healthy=proxies_healthy))
            await session.commit()
            if ips_healthy < 10:
                await _alert("Clean IP pool is nearly depleted (%d healthy)." % ips_healthy)
    except Exception as exc:
        await _finish_job(job, error=str(exc))
        return
    await _finish_job(job)


async def run_backup_now() -> tuple[bool, str]:
    import subprocess
    try:
        proc = subprocess.run(["/app/scripts/backup.sh"], capture_output=True, text=True, timeout=120)
        last = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "/app/backups"
        return proc.returncode == 0, last
    except Exception as exc:
        return False, str(exc)


async def job_backup() -> None:
    job = await _lock_job("backup")
    if job is None:
        return
    ok, path = await run_backup_now()
    await _finish_job(job, error=None if ok else "backup script failed")


def build_scheduler() -> AsyncIOScheduler:
    s = get_settings()
    sch = AsyncIOScheduler(timezone=s.timezone)
    # parse ip_scan_cron "m h1,h2 * * *" — minute + comma-separated hours
    parts = s.ip_scan_cron.split()
    minute = int(parts[0])
    hours = [int(h) for h in parts[1].split(",")]
    for h in hours:
        sch.add_job(job_ip_scan, CronTrigger(hour=h, minute=minute), id=f"ip_scan_{h}")
    sch.add_job(job_proxy_health, IntervalTrigger(minutes=s.proxy_health_interval_minutes), id="proxy_health")
    sch.add_job(job_endpoint_monitor, IntervalTrigger(minutes=s.endpoint_monitor_interval_minutes), id="endpoint_monitor")
    sch.add_job(job_sub_expiry, IntervalTrigger(minutes=s.sub_expiry_check_minutes), id="sub_expiry")
    sch.add_job(job_cleanup, IntervalTrigger(hours=s.cleanup_interval_hours), id="cleanup")
    sch.add_job(job_backup, CronTrigger(hour=s.backup_schedule_hour, minute=30), id="backup")
    sch.add_job(job_cf_verify, IntervalTrigger(hours=24), id="cf_verify")
    sch.add_job(job_metrics, IntervalTrigger(minutes=5), id="metrics")
    return sch


async def run() -> None:
    logging.basicConfig(level=get_settings().log_level,
                        format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    # recover stale jobs after restart
    async with SessionFactory() as session:
        await session.execute(update(BackgroundJob)
                              .where(BackgroundJob.status == "running")
                              .values(status="failed", error="interrupted by restart",
                                      finished_at=datetime.now(timezone.utc)))
        await session.commit()
    sch = build_scheduler()
    sch.start()
    log.info("worker scheduler started with %s jobs", len(sch.get_jobs()))
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(run())
