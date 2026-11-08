"""User-facing routers: main menu, create-VPN flow, configs, subs, tests, account, settings."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.bot import keyboards as kb
from app.bot.helpers import (ensure_user, get_user, guard_user,
                             lang_of, log_activity, rate_ok, user_stats)
from app.bot.i18n import t
from app.config import get_settings
from app.db.engine import SessionFactory
from app.db.models import (IpInventory, Subscription, VpnConfig, VpnProfile)
from app.subscriptions import service as subsrv
from app.vpn import validation
from app.vpn.engine import provision_profile

log = logging.getLogger("newvpn.bot.user")
router = Router()


class CreateFSM(StatesGroup):
    choose_protocol = State()
    profile_name = State()


class TestFSM(StatesGroup):
    pick_profile = State()


# ---------- /start ----------
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = await ensure_user(message.from_user)
    if user.status != "active":
        await message.answer(t(lang_of(user), "suspended"))
        return
    await log_activity(user.id, "start")
    await message.answer(t(lang_of(user), "welcome"))
    await message.answer(t(lang_of(user), "your_id", uid=user.id))
    await message.answer(t(lang_of(user), "main_menu_title"),
                         reply_markup=kb.main_menu(lang_of(user), is_admin=bool(user.is_admin)))


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    user = await ensure_user(message.from_user)
    await message.answer(t(lang_of(user), "main_menu_title"),
                         reply_markup=kb.main_menu(lang_of(user), is_admin=bool(user.is_admin)))


@router.callback_query(F.data == "menu:main")
async def cb_main(cb: CallbackQuery):
    user = await guard_user(cb)
    if user is None:
        await cb.answer(t("fa", "suspended"), show_alert=True)
        return
    if not rate_ok(user.id):
        await cb.answer()
        return
    await cb.message.edit_text(t(lang_of(user), "main_menu_title"),
                               reply_markup=kb.main_menu(lang_of(user), is_admin=bool(user.is_admin)))
    await cb.answer()


# ---------- create VPN ----------
@router.callback_query(F.data == "menu:create")
async def cb_create(cb: CallbackQuery, state: FSMContext):
    user = await guard_user(cb)
    if user is None or not rate_ok(user.id):
        await cb.answer()
        return
    lang = lang_of(user)
    s = get_settings()
    async with SessionFactory() as session:
        from sqlalchemy import func, select
        healthy = (await session.execute(
            select(func.count(IpInventory.id)).where(
                IpInventory.health_status.in_(("excellent", "good")))
        )).scalar_one()
    await state.set_state(CreateFSM.choose_protocol)
    await cb.message.edit_text(
        t(lang, "create_title", pool=healthy, domain="—" if not s.subscription_base_url else s.subscription_base_url,
          protocol=f"VLESS + Trojan"),
        reply_markup=kb.protocol_menu(lang),
    )
    await cb.answer()


@router.callback_query(CreateFSM.choose_protocol, F.data.startswith("proto:"))
async def cb_protocol(cb: CallbackQuery, state: FSMContext):
    user = await guard_user(cb)
    if user is None:
        await cb.answer()
        return
    lang = lang_of(user)
    protocol = cb.data.split(":", 1)[1]
    await state.update_data(protocol=protocol)
    await state.set_state(CreateFSM.profile_name)
    await cb.message.edit_text(t(lang, "create_profile_name"))
    await cb.answer()


@router.message(CreateFSM.profile_name, F.text)
async def fsm_profile_name(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    if user is None:
        return
    lang = lang_of(user)
    data = await state.get_data()
    name = (message.text or "").strip()[:64]
    if not name:
        await message.answer(t(lang, "invalid_input"))
        return
    await state.clear()
    progress = await message.answer(t(lang, "create_generating"))
    try:
        async with SessionFactory() as session:
            fresh = await session.get(User, user.id)
            result = await provision_profile(session, fresh, name, data["protocol"], None, with_cf=False)
            await session.commit()
    except Exception:
        log.exception("provision failed")
        await progress.edit_text(t(lang, "error_generic"))
        return

    s = get_settings()
    if result.count == 0:
        await progress.edit_text(t(lang, "create_failed"))
        return
    text = t(lang, "create_done", count=result.count) if result.count >= s.configs_per_profile \
        else t(lang, "create_partial", count=result.count, wanted=s.configs_per_profile,
               skipped="\n".join("• " + x for x in result.skipped[:4]))
    text += "\n\n" + t(lang, "sub_url", url=result.subscription_url)
    await progress.edit_text(text)
    # send each config link
    for c in result.configs:
        await message.answer(f"<code>{c.link}</code>")
    await log_activity(user.id, "provision", {"profile_id": result.profile_id, "count": result.count})


# ---------- my configs ----------
@router.callback_query(F.data == "menu:configs")
async def cb_configs(cb: CallbackQuery):
    user = await guard_user(cb)
    if user is None or not rate_ok(user.id):
        await cb.answer()
        return
    lang = lang_of(user)
    from sqlalchemy import select
    async with SessionFactory() as session:
        from app.db.models import VpnProfile
        rows = (await session.execute(
            select(VpnConfig).select_from(VpnConfig)
            .join(VpnProfile, VpnConfig.profile_id == VpnProfile.id)
            .where(VpnProfile.user_id == user.id, VpnConfig.status == "active")
            .order_by(VpnConfig.id).limit(10)
        )).scalars().all()
    if not rows:
        await cb.message.edit_text(t(lang, "my_configs_empty"), reply_markup=kb.back_menu(lang))
        await cb.answer()
        return
    lines = "\n".join(
        f"• <b>{c.name}</b> — {c.protocol.upper()}+{c.transport} @ {c.address}:{c.port} ({c.id})"
        for c in rows
    )
    await cb.message.edit_text(t(lang, "my_configs_title") + "\n\n" + lines +
                               "\n\n" + ("برای عملیات، شناسه کانفیگ را انتخاب کنید:" if lang == "fa" else "Pick a config ID:"),
                               reply_markup=kb.back_menu(lang))
    await cb.answer()


# ---------- my subscriptions ----------
@router.callback_query(F.data == "menu:subs")
async def cb_subs(cb: CallbackQuery):
    user = await guard_user(cb)
    if user is None or not rate_ok(user.id):
        await cb.answer()
        return
    lang = lang_of(user)
    from sqlalchemy import select
    async with SessionFactory() as session:
        rows = (await session.execute(
            select(Subscription).where(Subscription.user_id == user.id, Subscription.status == "active")
        )).scalars().all()
    if not rows:
        await cb.message.edit_text(t(lang, "my_subs_empty"), reply_markup=kb.back_menu(lang))
        await cb.answer()
        return
    for sub in rows[:5]:
        url = subsrv_sub_url(sub.token)
        await cb.message.answer(t(lang, "sub_url", url=url),
                                reply_markup=kb.sub_actions(lang, sub.id, sub.token))
    await cb.answer()


def subsrv_sub_url(token: str) -> str:
    from app.vpn.engine import sub_url
    return sub_url(token)


@router.callback_query(F.data.startswith("sub:rotate:"))
async def cb_sub_rotate(cb: CallbackQuery):
    user = await guard_user(cb)
    if user is None:
        await cb.answer()
        return
    lang = lang_of(user)
    sub_id = int(cb.data.split(":")[2])
    async with SessionFactory() as session:
        sub = await session.get(Subscription, sub_id)
        if sub is None or sub.user_id != user.id:
            await cb.answer("not found", show_alert=True)
            return
        await subsrv.rotate_token(session, sub)
        await session.commit()
        url = subsrv_sub_url(sub.token)
    await cb.message.edit_text(t(lang, "sub_rotated", url=url))
    await cb.answer()


@router.callback_query(F.data.startswith("sub:revoke:"))
async def cb_sub_revoke(cb: CallbackQuery):
    user = await guard_user(cb)
    if user is None:
        await cb.answer()
        return
    lang = lang_of(user)
    sub_id = int(cb.data.split(":")[2])
    async with SessionFactory() as session:
        sub = await session.get(Subscription, sub_id)
        if sub is None or sub.user_id != user.id:
            await cb.answer("not found", show_alert=True)
            return
        await subsrv.revoke(session, sub)
        await session.commit()
    await cb.message.edit_text(t(lang, "sub_revoked"))
    await cb.answer()


# ---------- connection test ----------
@router.callback_query(F.data == "menu:test")
async def cb_test(cb: CallbackQuery):
    user = await guard_user(cb)
    if user is None or not rate_ok(user.id):
        await cb.answer()
        return
    lang = lang_of(user)
    from sqlalchemy import select
    async with SessionFactory() as session:
        profiles = (await session.execute(
            select(VpnProfile.id, VpnProfile.name).where(
                VpnProfile.user_id == user.id, VpnProfile.status == "active")
        )).all()
    if not profiles:
        await cb.message.edit_text(t(lang, "my_configs_empty"), reply_markup=kb.back_menu(lang))
        await cb.answer()
        return
    await cb.message.edit_text(t(lang, "conn_test_title"),
                               reply_markup=kb.profile_pick(lang, [(pid, name) for pid, name in profiles], prefix="cprof"))
    await cb.answer()


@router.callback_query(F.data.startswith("cprof:"))
async def cb_test_profile(cb: CallbackQuery):
    user = await guard_user(cb)
    if user is None or not rate_ok(user.id):
        await cb.answer()
        return
    lang = lang_of(user)
    pid = int(cb.data.split(":")[1])
    from sqlalchemy import select
    async with SessionFactory() as session:
        cfgs = (await session.execute(
            select(VpnConfig).where(VpnConfig.profile_id == pid, VpnConfig.status == "active")
        )).scalars().all()
    lines = []
    for c in cfgs[:6]:
        res = await validation.validate_endpoint(c.address, c.port, c.transport,
                                                 sni=c.sni, path=c.path, host_header=c.host_header)
        c.last_check_at = datetime.now(timezone.utc)
        c.last_check_status = "ok" if res.ok else "fail"
        c.last_latency_ms = res.latency_ms
        lines.append(f"• {c.name}: {'✅' if res.ok else '❌'} {res.latency_ms or '—'}ms ({res.check_class}) {res.detail}")
    async with SessionFactory() as session:
        for c in cfgs[:6]:
            await session.merge(c)
        await session.commit()
    body = "\n".join(lines) or "—"
    await cb.message.edit_text(
        "🧪 <b>Endpoint check</b>\n\n" + body +
        "\n\n<i>(" + ("تست endpoint است — تونل کامل VPN نیست" if lang == "fa" else "endpoint-level check, not a full tunnel test") + ")</i>"
    )
    await cb.answer()


# ---------- clean ip pool ----------
@router.callback_query(F.data == "menu:ippool")
async def cb_ippool(cb: CallbackQuery):
    user = await guard_user(cb)
    if user is None or not rate_ok(user.id):
        await cb.answer()
        return
    lang = lang_of(user)
    from sqlalchemy import func, select
    async with SessionFactory() as session:
        by = dict((await session.execute(
            select(IpInventory.health_status, func.count(IpInventory.id))
            .group_by(IpInventory.health_status)
        )).all())
        from app.db.models import IpScanHistory
        last = (await session.execute(
            select(IpScanHistory).where(IpScanHistory.status == "completed")
            .order_by(IpScanHistory.id.desc()).limit(1)
        )).scalar_one_or_none()
    text = t(lang, "ip_pool_title",
             excellent=by.get("excellent", 0), good=by.get("good", 0),
             average=by.get("average", 0), unhealthy=by.get("unhealthy", 0),
             last_scan=(last.started_at.strftime("%Y-%m-%d %H:%M UTC") if last else "—"))
    await cb.message.edit_text(text, reply_markup=kb.back_menu(lang))
    await cb.answer()


# ---------- account ----------
@router.callback_query(F.data == "menu:account")
async def cb_account(cb: CallbackQuery):
    user = await guard_user(cb)
    if user is None or not rate_ok(user.id):
        await cb.answer()
        return
    lang = lang_of(user)
    cfgs, subs = await user_stats(user.id)
    await cb.message.edit_text(
        t(lang, "account_title", uid=user.id, lang=user.language, status=user.status,
          configs=cfgs, subs=subs, since=user.created_at.strftime("%Y-%m-%d") if user.created_at else "—"),
        reply_markup=kb.back_menu(lang),
    )
    await cb.answer()


# ---------- settings & language ----------
@router.callback_query(F.data == "menu:settings")
async def cb_settings(cb: CallbackQuery):
    user = await guard_user(cb)
    if user is None or not rate_ok(user.id):
        await cb.answer()
        return
    lang = lang_of(user)
    await cb.message.edit_text(t(lang, "settings_title", lang=user.language),
                               reply_markup=kb.language_menu(lang))
    await cb.answer()


@router.callback_query(F.data == "menu:language")
async def cb_language(cb: CallbackQuery):
    user = await guard_user(cb)
    if user is None or not rate_ok(user.id):
        await cb.answer()
        return
    lang = lang_of(user)
    await cb.message.edit_text(t(lang, "settings_title"), reply_markup=kb.language_menu(lang))
    await cb.answer()


@router.callback_query(F.data.startswith("lang:"))
async def cb_set_lang(cb: CallbackQuery):
    user = await guard_user(cb)
    if user is None or not rate_ok(user.id):
        await cb.answer()
        return
    lang = cb.data.split(":")[1]
    async with SessionFactory() as session:
        u = await session.get(User, user.id)
        u.language = lang
        await session.commit()
    await cb.message.edit_text(t(lang, "language_set", lang="فارسی" if lang == "fa" else "English"))
    await cb.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(cb: CallbackQuery):
    await cb.answer()


# ---------- placeholders for section menus that live in dedicated routers ----------
@router.callback_query(F.data.in_({"menu:proxy", "menu:static"}))
async def cb_proxy_info(cb: CallbackQuery):
    user = await guard_user(cb)
    if user is None or not rate_ok(user.id):
        await cb.answer()
        return
    lang = lang_of(user)
    body_fa = ("🔗 <b>Proxy Chain / Static IP</b>\n\n"
               "این قابلیت ترافیک VPN شما را از یک IP خروجی ثابت عبور می‌دهد.\n\n"
               "برای فعال‌سازی، ادمین باید Proxy سالم (SOCKS5/HTTP) در استخر ثبت کرده باشد.\n"
               "از 🟢 ساخت VPN با گزینه ترکیبی شروع کنید یا با پشتیبانی تماس بگیرید.")
    body_en = ("🔗 <b>Proxy Chain / Static IP</b>\n\n"
               "Routes your VPN traffic through a dedicated static egress IP.\n\n"
               "An admin must register healthy SOCKS5/HTTP upstreams first.\n"
               "Start with 🟢 Create VPN or contact support.")
    await cb.message.edit_text(body_fa if lang == "fa" else body_en, reply_markup=kb.back_menu(lang))
    await cb.answer()
