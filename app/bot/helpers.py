"""Shared bot helpers — user provisioning, auth checks, activity logging."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram.types import Message, CallbackQuery
from sqlalchemy import func, select

from app.config import get_settings
from app.bot.i18n import detect_language, t
from app.db.engine import SessionFactory
from app.db.models import AuditLog, Subscription, User, UserActivity, VpnConfig

log = logging.getLogger("newvpn.bot")

# simple in-memory flood gate (per process): uid -> last ts
_last_cb: dict[int, float] = {}


def rate_ok(uid: int, min_interval: float = 0.6) -> bool:
    import time
    now = time.monotonic()
    if now - _last_cb.get(uid, 0) < min_interval:
        return False
    _last_cb[uid] = now
    return True


async def ensure_user(tg_user) -> User:
    """Fetch or create the user row; refresh language from locale when unset."""
    s = get_settings()
    async with SessionFactory() as session:
        user = await session.get(User, tg_user.id)
        if user is None:
            user = User(
                id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                language=detect_language(tg_user.language_code),
                is_admin=tg_user.id in s.admin_ids,
                last_seen_at=datetime.now(timezone.utc),
            )
            session.add(user)
            await session.commit()
        else:
            user.username = tg_user.username or user.username
            user.first_name = tg_user.first_name or user.first_name
            user.last_seen_at = datetime.now(timezone.utc)
            if tg_user.id in s.admin_ids and not user.is_admin:
                user.is_admin = True
            await session.commit()
            await session.refresh(user)
        return user


async def get_user(uid: int) -> User | None:
    async with SessionFactory() as session:
        return await session.get(User, uid)


async def log_activity(uid: int, action: str, details: dict | None = None) -> None:
    async with SessionFactory() as session:
        session.add(UserActivity(user_id=uid, action=action, details=details))
        await session.commit()


async def audit(admin_id: int, action: str, target_type: str | None = None,
                target_id: str | None = None, details: dict | None = None) -> None:
    async with SessionFactory() as session:
        session.add(AuditLog(admin_id=admin_id, action=action, target_type=target_type,
                             target_id=target_id, details=details))
        await session.commit()


async def user_stats(uid: int) -> tuple[int, int]:
    async with SessionFactory() as session:
        cfgs = (await session.execute(
            select(func.count(VpnConfig.id)).where(
                VpnConfig.profile_id.in_(select(VpnConfig.profile_id)),
            )
        )).scalar_one()
        # count configs belonging to this user's profiles via join on profiles.user_id
        from app.db.models import VpnProfile
        cfgs = (await session.execute(
            select(func.count(VpnConfig.id))
            .select_from(VpnConfig)
            .join(VpnProfile, VpnConfig.profile_id == VpnProfile.id)
            .where(VpnProfile.user_id == uid, VpnConfig.status == "active")
        )).scalar_one()
        subs = (await session.execute(
            select(func.count(Subscription.id))
            .where(Subscription.user_id == uid, Subscription.status == "active")
        )).scalar_one()
        return cfgs, subs


async def is_admin(uid: int) -> bool:
    user = await get_user(uid)
    return bool(user and user.is_admin)


async def guard_user(obj) -> User | None:
    """Resolve & check the user for a message/callback; returns None when suspended."""
    tg = obj.from_user
    user = await ensure_user(tg)
    if user.status != "active":
        return None
    return user


def lang_of(user: User) -> str:
    return user.language or get_settings().default_language
