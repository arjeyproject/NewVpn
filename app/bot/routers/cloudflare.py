"""Cloudflare account connection flow — secure token handling inside Telegram."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.bot import keyboards as kb
from app.bot.helpers import get_user, guard_user, lang_of, log_activity
from app.bot.i18n import t
from app.cloudflare.client import CloudflareClient, CloudflareError
from app.db.engine import SessionFactory
from app.db.models import CloudflareAccount, CloudflareZone, Domain
from app.security import crypto

log = logging.getLogger("newvpn.bot.cf")
router = Router()


class CfFSM(StatesGroup):
    waiting_token = State()


@router.callback_query(F.data == "menu:cf")
async def cb_cf(cb: CallbackQuery):
    user = await guard_user(cb)
    if user is None:
        await cb.answer()
        return
    lang = lang_of(user)
    async with SessionFactory() as session:
        accounts = (await session.execute(
            select(CloudflareAccount).where(
                CloudflareAccount.user_id == user.id, CloudflareAccount.status == "active")
        )).scalars().all()
    if accounts:
        zones_count = sum(len((await session.execute(
            select(CloudflareZone).where(CloudflareZone.account_id == a.id))).scalars().all())
            for a in accounts)
        await cb.message.edit_text(
            t(lang, "cf_connected", name=accounts[0].account_name or accounts[0].label, zones=zones_count),
            reply_markup=kb.cf_menu(lang, True, accounts[0].account_name or accounts[0].label))
    else:
        await cb.message.edit_text(t(lang, "cf_none"), reply_markup=kb.cf_menu(lang, False))
    await cb.answer()


@router.callback_query(F.data == "cf:connect")
async def cb_cf_connect(cb: CallbackQuery, state: FSMContext):
    user = await guard_user(cb)
    if user is None:
        await cb.answer()
        return
    lang = lang_of(user)
    await state.set_state(CfFSM.waiting_token)
    await cb.message.edit_text(t(lang, "cf_guide") + "\n\n" + t(lang, "cf_send_token"))
    await cb.answer()


@router.message(CfFSM.waiting_token, F.text)
async def fsm_cf_token(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    if user is None:
        return
    lang = lang_of(user)
    token = (message.text or "").strip()
    await state.clear()
    try:
        await message.delete()  # never keep the token in chat history
    except Exception:
        pass
    if token.startswith("/"):
        return
    progress = await message.answer(t(lang, "cf_verifying"))
    try:
        client = CloudflareClient(token)
        info = await client.verify_token()
        if not info.valid:
            raise CloudflareError("token status is not active")
        zones = await client.get_zones()
    except CloudflareError as exc:
        await progress.edit_text(t(lang, "cf_invalid_token", error=exc.message))
        return
    except Exception:
        log.exception("cf verify failed")
        await progress.edit_text(t(lang, "error_generic"))
        return

    async with SessionFactory() as session:
        account = CloudflareAccount(
            user_id=user.id,
            label=(info.account_name or "cloudflare")[:64],
            account_id_cf=info.account_id or None,
            account_name=info.account_name or "cloudflare",
            api_token_encrypted=crypto.encrypt_secret(token),
            status="pending",
            verified_at=None,
        )
        session.add(account)
        await session.flush()
        for z in zones:
            session.add(CloudflareZone(
                account_id=account.id, zone_id_cf=z.zone_id, name=z.name,
                status=z.status, verified=z.can_edit_dns,
            ))
        await session.commit()
        account_id = account.id
    await log_activity(user.id, "cf_account_added", {"account_id": account_id, "zones": len(zones)})
    await progress.edit_text(t(lang, "cf_verified", name=info.account_name or "cloudflare"))

    editable = [z for z in zones if z.can_edit_dns]
    if editable:
        await message.answer(t(lang, "cf_pick_zone"),
                             reply_markup=kb.zone_menu(lang, [(z.zone_id, z.name) for z in editable]))
    else:
        await message.answer(t(lang, "cf_zone_failed", error="no zone with DNS edit permission"))


@router.callback_query(F.data.startswith("zone:"))
async def cb_pick_zone(cb: CallbackQuery):
    user = await guard_user(cb)
    if user is None:
        await cb.answer()
        return
    lang = lang_of(user)
    zone_id_cf = cb.data.split(":", 1)[1]
    async with SessionFactory() as session:
        zone = (await session.execute(
            select(CloudflareZone).where(CloudflareZone.zone_id_cf == zone_id_cf)
        )).scalar_one_or_none()
        if zone is None or zone.account.user_id != user.id:
            await cb.answer("not found", show_alert=True)
            return
        client = CloudflareClient(crypto.decrypt_secret(zone.account.api_token_encrypted))
        validation_result = await client.validate_zone_for_dns(zone_id_cf)
        if validation_result.errors or validation_result.zone is None:
            await cb.message.edit_text(t(lang, "cf_zone_failed", error="\n".join(validation_result.errors)))
            await cb.answer()
            return
        zone.verified = True
        zone.account.status = "active"
        zone.account.verified_at = zone.account.verified_at or datetime.now(timezone.utc)
        zone.account.last_check_at = datetime.now(timezone.utc)
        # register domain usable for provisioning/sub
        exists = (await session.execute(
            select(Domain).where(Domain.name == zone.name))).scalar_one_or_none()
        if exists is None:
            session.add(Domain(zone_id=zone.id, owner_user_id=user.id, name=zone.name, purpose="entry"))
        await session.commit()
    await log_activity(user.id, "cf_zone_verified", {"zone": zone.name})
    await cb.message.edit_text(t(lang, "cf_zone_ok", zone=zone.name))
    await cb.answer()


@router.callback_query(F.data.in_({"cf:disconnect", "cf:cancel"}))
async def cf_disconnect(cb: CallbackQuery):
    user = await guard_user(cb)
    if user is None:
        await cb.answer()
        return
    lang = lang_of(user)
    if cb.data == "cf:disconnect":
        async with SessionFactory() as session:
            accounts = (await session.execute(
                select(CloudflareAccount).where(CloudflareAccount.user_id == user.id))).scalars().all()
            for a in accounts:
                a.status = "revoked"
                a.revoked_at = datetime.now(timezone.utc)
            await session.commit()
        await log_activity(user.id, "cf_account_revoked")
        await cb.message.edit_text(t(lang, "cf_deleted"), reply_markup=kb.cf_menu(lang, False))
    else:
        await cb.message.edit_text(t(lang, "cf_title"), reply_markup=kb.cf_menu(lang, False))
    await cb.answer()
