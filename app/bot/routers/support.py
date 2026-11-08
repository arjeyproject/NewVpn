"""Support system — tickets, categories, admin notification, diagnostics."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from app.bot import keyboards as kb
from app.bot.helpers import get_user, guard_user, lang_of, log_activity
from app.bot.i18n import t
from app.config import get_settings
from app.db.engine import SessionFactory
from app.db.models import SupportTicket, TicketMessage

log = logging.getLogger("newvpn.bot.support")
router = Router()


class SupFSM(StatesGroup):
    category = State()
    subject = State()
    message = State()


@router.callback_query(F.data == "menu:support")
async def cb_support(cb: CallbackQuery):
    user = await guard_user(cb)
    if user is None or not user_status_ok(user.id):
        await cb.answer()
        return
    lang = lang_of(user)
    await cb.message.edit_text(t(lang, "support_title", handle=get_settings().support_handle),
                               reply_markup=kb.support_menu(lang))
    await cb.answer()


def user_status_ok(uid: int) -> bool:
    return True  # guard_user already validated


@router.callback_query(F.data == "sup:new")
async def cb_sup_new(cb: CallbackQuery, state: FSMContext):
    user = await guard_user(cb)
    if user is None:
        await cb.answer()
        return
    lang = lang_of(user)
    await state.set_state(SupFSM.category)
    await cb.message.edit_text(t(lang, "support_ask_category"), reply_markup=kb.support_categories(lang))
    await cb.answer()


@router.callback_query(SupFSM.category, F.data.startswith("sup:cat:"))
async def cb_sup_cat(cb: CallbackQuery, state: FSMContext):
    user = await guard_user(cb)
    if user is None:
        await cb.answer()
        return
    lang = lang_of(user)
    category = cb.data.split(":")[2]
    await state.update_data(category=category)
    await state.set_state(SupFSM.subject)
    await cb.message.edit_text(t(lang, "support_ask_subject"))
    await cb.answer()


@router.message(SupFSM.subject, F.text)
async def fsm_sup_subject(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    if user is None:
        return
    lang = lang_of(user)
    subject = (message.text or "").strip()[:200]
    if not subject:
        await message.answer(t(lang, "invalid_input"))
        return
    await state.update_data(subject=subject)
    await state.set_state(SupFSM.message)
    await message.answer(t(lang, "support_ask_message"))


@router.message(SupFSM.message, F.text)
async def fsm_sup_message(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    if user is None:
        return
    lang = lang_of(user)
    text = (message.text or "").strip()[:4000]
    data = await state.get_data()
    await state.clear()
    if not text:
        await message.answer(t(lang, "invalid_input"))
        return
    async with SessionFactory() as session:
        ticket = SupportTicket(user_id=user.id, category=data.get("category", "general"),
                               subject=data.get("subject", "—"))
        session.add(ticket)
        await session.flush()
        session.add(TicketMessage(ticket_id=ticket.id, sender="user", sender_id=user.id, message=text))
        await session.commit()
        tid = ticket.id
    await log_activity(user.id, "ticket_created", {"ticket_id": tid})
    # notify admins (best effort)
    s = get_settings()
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    try:
        bot = Bot(token=s.bot_token, default=DefaultBotProperties(parse_mode="HTML"))
        for admin_id in s.admin_ids:
            try:
                await bot.send_message(
                    admin_id,
                    f"🎫 <b>تیکت جدید #{tid}</b>\nاز: {user.id} (@{user.username or '—'})\nدسته: {ticket_category_label(data.get('category', 'general'))}\nموضوع: {data.get('subject')}\n\n{text[:1000]}",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="پاسخ از طریق ریپلای", callback_data="noop")]]),
                )
            except Exception:
                pass
        await bot.session.close()
    except Exception:
        pass
    await message.answer(t(lang, "support_created", tid=tid))


def ticket_category_label(cat: str) -> str:
    return {"connection": "اتصال", "cloudflare": "Cloudflare", "billing": "اشتراک", "general": "عمومی"}.get(cat, cat)


@router.callback_query(F.data == "sup:list")
async def cb_sup_list(cb: CallbackQuery):
    user = await guard_user(cb)
    if user is None or not user_status_ok(user.id):
        await cb.answer()
        return
    lang = lang_of(user)
    async with SessionFactory() as session:
        tickets = (await session.execute(
            select(SupportTicket).where(SupportTicket.user_id == user.id)
            .order_by(SupportTicket.id.desc()).limit(10))).scalars().all()
    if not tickets:
        await cb.message.edit_text("—", reply_markup=kb.back_menu(lang, "menu:support"))
        await cb.answer()
        return
    icon = {"open": "🟡", "answered": "🟢", "closed": "⚪️"}
    lines = "\n".join(f"{icon.get(tk.status, '⚪️')} #{tk.id} — {tk.subject} [{tk.status}]"
                      for tk in tickets)
    await cb.message.edit_text("📂 <b>My tickets</b>\n\n" + lines,
                               reply_markup=kb.back_menu(lang, "menu:support"))
    await cb.answer()


@router.callback_query(F.data == "sup:faq")
async def cb_sup_faq(cb: CallbackQuery):
    user = await guard_user(cb)
    if user is None or not user_status_ok(user.id):
        await cb.answer()
        return
    lang = lang_of(user)
    from app.bot.routers.tutorials import CONTENT
    body = CONTENT.get(lang, CONTENT["fa"]).get("faq", "")
    await cb.message.edit_text(t(lang, "tut_placeholder",
                                 title="FAQ" if lang == "en" else "سوالات متداول", body=body),
                               reply_markup=kb.back_menu(lang, "menu:support"))
    await cb.answer()


@router.message(F.text == "/cancel")
async def cmd_cancel(message: Message):
    user = await get_user(message.from_user.id)
    lang = lang_of(user) if user else "fa"
    await message.answer("✅ " + ("انصراف داده شد" if lang == "fa" else "Cancelled"),
                         reply_markup=kb.main_menu(lang, is_admin=bool(user and user.is_admin)))
