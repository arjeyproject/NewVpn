"""Administrator dashboard — full system control, audit logged."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select

from app.bot import keyboards as kb
from app.bot.helpers import audit, get_user, lang_of, rate_ok
from app.bot.i18n import t
from app.config import get_settings
from app.db.engine import SessionFactory
from app.db.models import (AuditLog, BackgroundJob, CloudflareAccount, IpInventory,
                           ProxyInventory, Subscription, User, VpnConfig)

log = logging.getLogger("newvpn.bot.admin")
router = Router()


def _is_admin(uid: int) -> bool:
    return uid in get_settings().admin_ids


class AdmFSM(StatesGroup):
    user_search = State()
    broadcast = State()
    proxy_add = State()


@router.callback_query(F.data == "admin:panel")
async def cb_admin_panel(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        await cb.answer(t("fa", "admin_only"), show_alert=True)
        return
    lang = lang_of(await get_user(cb.from_user.id)) or "fa"
    async with SessionFactory() as session:
        users_total = (await session.execute(select(func.count(User.id)))).scalar_one()
        users_active = (await session.execute(
            select(func.count(User.id)).where(User.status == "active"))).scalar_one()
        cfgs = (await session.execute(
            select(func.count(VpnConfig.id)).where(VpnConfig.status == "active"))).scalar_one()
        subs = (await session.execute(
            select(func.count(Subscription.id)).where(Subscription.status == "active"))).scalar_one()
        cf = (await session.execute(
            select(func.count(CloudflareAccount.id)).where(CloudflareAccount.status == "active"))).scalar_one()
        ips = (await session.execute(
            select(func.count(IpInventory.id)).where(
                IpInventory.health_status.in_(("excellent", "good"))))).scalar_one()
        proxies = (await session.execute(
            select(func.count(ProxyInventory.id)).where(ProxyInventory.status == "healthy"))).scalar_one()
        jobs = (await session.execute(
            select(func.count(BackgroundJob.id)).where(
                BackgroundJob.status == "running"))).scalar_one()
    await cb.message.edit_text(
        t(lang, "adm_title", users=users_total, active=users_active, configs=cfgs, subs=subs,
          cf=cf, ips=ips, proxies=proxies, jobs=jobs),
        reply_markup=kb.admin_panel(lang),
    )
    await cb.answer()


@router.callback_query(F.data == "adm:users")
async def cb_adm_users(cb: CallbackQuery, state: FSMContext):
    if not _is_admin(cb.from_user.id):
        await cb.answer(t("fa", "admin_only"), show_alert=True)
        return
    lang = lang_of(await get_user(cb.from_user.id)) or "fa"
    await state.set_state(AdmFSM.user_search)
    await cb.message.edit_text(t(lang, "adm_user_search"))
    await cb.answer()


@router.message(AdmFSM.user_search, F.text)
async def fsm_adm_user_search(message: Message, state: FSMContext):
    lang = lang_of(await get_user(message.from_user.id)) or "fa"
    await state.clear()
    if not _is_admin(message.from_user.id):
        return
    text = (message.text or "").strip()
    async with SessionFactory() as session:
        if text.isdigit():
            user = await session.get(User, int(text))
        else:
            user = (await session.execute(
                select(User).where(User.username == text.lstrip("@")))).scalar_one_or_none()
        if user is None:
            await message.answer(t(lang, "invalid_input"))
            return
        from app.db.models import VpnProfile
        cfgs = (await session.execute(
            select(func.count(VpnConfig.id)).select_from(VpnConfig)
            .join(VpnProfile, VpnConfig.profile_id == VpnProfile.id)
            .where(VpnProfile.user_id == user.id))).scalar_one()
        subs = (await session.execute(
            select(func.count(Subscription.id))
            .where(Subscription.user_id == user.id, Subscription.status == "active"))).scalar_one()
    await message.answer(
        t(lang, "adm_user_card", uid=user.id, name=user.username or user.first_name or "—",
          status=user.status, configs=cfgs, subs=subs),
        reply_markup=kb.admin_user_actions(lang, user.id, suspended=user.status != "active"),
    )


@router.callback_query(F.data.startswith("adm:usus:"))
async def cb_adm_suspend(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        await cb.answer(t("fa", "admin_only"), show_alert=True)
        return
    uid = int(cb.data.split(":")[2])
    async with SessionFactory() as session:
        user = await session.get(User, uid)
        user.status = "suspended"
        await session.commit()
    await audit(cb.from_user.id, "user_suspend", "user", str(uid))
    await cb.message.edit_text(t("fa", "adm_done"))
    await cb.answer()


@router.callback_query(F.data.startswith("adm:uact:"))
async def cb_adm_activate(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        await cb.answer(t("fa", "admin_only"), show_alert=True)
        return
    uid = int(cb.data.split(":")[2])
    async with SessionFactory() as session:
        user = await session.get(User, uid)
        user.status = "active"
        await session.commit()
    await audit(cb.from_user.id, "user_activate", "user", str(uid))
    await cb.message.edit_text(t("fa", "adm_done"))
    await cb.answer()


@router.callback_query(F.data == "adm:ippool")
async def cb_adm_ippool(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        await cb.answer(t("fa", "admin_only"), show_alert=True)
        return
    lang = lang_of(await get_user(cb.from_user.id)) or "fa"
    async with SessionFactory() as session:
        best = (await session.execute(
            select(IpInventory).where(IpInventory.tcp_connect == True)  # noqa: E712
            .order_by(IpInventory.quality_score.desc()).limit(10))).scalars().all()
        by = dict((await session.execute(
            select(IpInventory.health_status, func.count(IpInventory.id))
            .group_by(IpInventory.health_status))).all())
    lines = "\n".join(f"• {r.address}:{r.port} — {r.health_status} ({r.quality_score}) {r.latency_ms or '—'}ms"
                      for r in best) or "—"
    await cb.message.edit_text(
        t(lang, "ip_pool_title", excellent=by.get("excellent", 0), good=by.get("good", 0),
          average=by.get("average", 0), unhealthy=by.get("unhealthy", 0), last_scan="") +
        "\n\n<b>Top:</b>\n" + lines,
        reply_markup=kb.back_menu(lang, "admin:panel"),
    )
    await cb.answer()


@router.callback_query(F.data == "adm:scan")
async def cb_adm_scan(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        await cb.answer(t("fa", "admin_only"), show_alert=True)
        return
    from app.worker.jobs import enqueue_ip_scan
    started = await enqueue_ip_scan(trigger="manual")
    await cb.answer(t("fa", "adm_job_running") if started else "⏳ already running", show_alert=True)


@router.callback_query(F.data == "adm:backup")
async def cb_adm_backup(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        await cb.answer(t("fa", "admin_only"), show_alert=True)
        return
    from app.worker.jobs import run_backup_now
    ok, path = await run_backup_now()
    await cb.answer(("✅ " + path) if ok else "❌ backup failed", show_alert=True)


@router.callback_query(F.data == "adm:audit")
async def cb_adm_audit(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        await cb.answer(t("fa", "admin_only"), show_alert=True)
        return
    async with SessionFactory() as session:
        rows = (await session.execute(
            select(AuditLog).order_by(AuditLog.id.desc()).limit(15))).scalars().all()
    lines = "\n".join(
        f"• [{r.created_at.strftime('%m-%d %H:%M')}] {r.action} {r.target_type or ''} {r.target_id or ''} by {r.admin_id}"
        for r in rows) or "—"
    await cb.message.edit_text("📜 <b>Audit log</b>\n\n" + lines,
                               reply_markup=kb.back_menu("fa", "admin:panel"))
    await cb.answer()


@router.callback_query(F.data == "adm:proxy")
async def cb_adm_proxy(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        await cb.answer(t("fa", "admin_only"), show_alert=True)
        return
    async with SessionFactory() as session:
        rows = (await session.execute(select(ProxyInventory))).scalars().all()
    lines = "\n".join(
        f"• {p.name} [{p.protocol}] {p.host}:{p.port} — {p.status} egress:{p.egress_ip or '—'}"
        for p in rows) or "—"
    await cb.message.edit_text(
        "🔗 <b>Proxy inventory</b>\n\n" + lines +
        "\n\n<i>Add via scripts/add_proxy.py or docker exec</i>",
        reply_markup=kb.back_menu("fa", "admin:panel"),
    )
    await cb.answer()


@router.callback_query(F.data == "adm:settings")
async def cb_adm_settings(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        await cb.answer(t("fa", "admin_only"), show_alert=True)
        return
    s = get_settings()
    await cb.message.edit_text(
        "⚙️ <b>System settings (env-driven)</b>\n\n"
        f"configs_per_profile: {s.configs_per_profile}\n"
        f"config_expiry_days: {s.config_expiry_days}\n"
        f"ip_scan_cron: <code>{s.ip_scan_cron}</code>\n"
        f"ip_scan_sample_per_range: {s.ip_scan_sample_per_range}\n"
        f"ip_scan_concurrency: {s.ip_scan_concurrency}\n"
        f"xray ports: reality={s.xray_reality_port} ws={s.xray_ws_port} trojan={s.xray_trojan_port}\n"
        f"reality_dest: <code>{s.reality_dest}</code>\n\n"
        "<i>Edit .env on the server and restart containers to apply.</i>",
        reply_markup=kb.back_menu("fa", "admin:panel"),
    )
    await cb.answer()


@router.callback_query(F.data == "adm:broadcast")
async def cb_adm_broadcast(cb: CallbackQuery, state: FSMContext):
    if not _is_admin(cb.from_user.id):
        await cb.answer(t("fa", "admin_only"), show_alert=True)
        return
    await state.set_state(AdmFSM.broadcast)
    await cb.message.edit_text("📣 متن پیام همگانی را بفرستید: /cancel برای انصراف")
    await cb.answer()


@router.message(AdmFSM.broadcast, F.text)
async def fsm_broadcast(message: Message, state: FSMContext):
    await state.clear()
    if not _is_admin(message.from_user.id):
        return
    sent = failed = 0
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from app.config import get_settings as gs
    bot = Bot(token=gs().bot_token, default=DefaultBotProperties(parse_mode="HTML"))
    async with SessionFactory() as session:
        users = (await session.execute(select(User.id).where(User.status == "active"))).scalars().all()
    for uid in users:
        try:
            await bot.send_message(uid, message.html_text or message.text)
            sent += 1
        except Exception:
            failed += 1
    await audit(message.from_user.id, "broadcast", details={"sent": sent, "failed": failed})
    await message.answer(f"📣 sent={sent} failed={failed}")
