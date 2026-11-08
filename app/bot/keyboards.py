"""Inline keyboards — symmetric layouts, emoji color coding.

Note on colors: Telegram's Bot API has no native color property for inline
buttons (verified against core.telegram.org/bots/api). Color semantics are
expressed with emoji prefixes (🟢 success/create, 🔵 navigation, 🔴 destructive)
as the suggested layout in the product spec does.
"""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.i18n import t


def main_menu(lang: str, is_admin: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=t(lang, "menu_create"), callback_data="menu:create")],
        [
            InlineKeyboardButton(text=t(lang, "menu_my_configs"), callback_data="menu:configs"),
            InlineKeyboardButton(text=t(lang, "menu_my_subs"), callback_data="menu:subs"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "menu_proxy_chain"), callback_data="menu:proxy"),
            InlineKeyboardButton(text=t(lang, "menu_static_ip"), callback_data="menu:static"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "menu_ip_pool"), callback_data="menu:ippool"),
            InlineKeyboardButton(text=t(lang, "menu_conn_test"), callback_data="menu:test"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "menu_cf_account"), callback_data="menu:cf"),
            InlineKeyboardButton(text=t(lang, "menu_my_account"), callback_data="menu:account"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "menu_tutorials"), callback_data="menu:tutorials"),
            InlineKeyboardButton(text=t(lang, "menu_support"), callback_data="menu:support"),
        ],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text="🛠 " + ("پنل ادمین" if lang == "fa" else "Admin Panel"),
                                          callback_data="admin:panel")])
    rows.append([
        InlineKeyboardButton(text=t(lang, "menu_settings"), callback_data="menu:settings"),
        InlineKeyboardButton(text=t(lang, "menu_language"), callback_data="menu:language"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def language_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇮🇷 فارسی", callback_data="lang:fa"),
         InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en")],
        [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="menu:main")],
    ])


def protocol_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "create_vless"), callback_data="proto:vless")],
        [InlineKeyboardButton(text=t(lang, "create_trojan"), callback_data="proto:trojan")],
        [InlineKeyboardButton(text=t(lang, "create_mixed"), callback_data="proto:mixed")],
        [InlineKeyboardButton(text=t(lang, "btn_cancel"), callback_data="menu:main")],
    ])


def back_menu(lang: str, target: str = "menu:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data=target)],
    ])


def cf_menu(lang: str, connected: bool, account_label: str | None = None) -> InlineKeyboardMarkup:
    rows = []
    if connected:
        rows.append([InlineKeyboardButton(text=f"✅ {account_label or 'ACTIVE'}", callback_data="noop")])
        rows.append([InlineKeyboardButton(text=t(lang, "cf_disconnect_btn"), callback_data="cf:disconnect")])
    else:
        rows.append([InlineKeyboardButton(text=t(lang, "cf_connect_btn"), callback_data="cf:connect")])
    rows.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def zone_menu(lang: str, zones: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=name, callback_data=f"zone:{zone_id}")] for zone_id, name in zones[:10]]
    rows.append([InlineKeyboardButton(text=t(lang, "btn_cancel"), callback_data="cf:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def config_actions(lang: str, config_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "cfg_copy"), callback_data=f"cfg:link:{config_id}"),
         InlineKeyboardButton(text=t(lang, "cfg_qr"), callback_data=f"cfg:qr:{config_id}")],
        [InlineKeyboardButton(text=t(lang, "cfg_test"), callback_data=f"cfg:test:{config_id}"),
         InlineKeyboardButton(text=t(lang, "cfg_delete"), callback_data=f"cfg:del:{config_id}")],
        [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="menu:configs")],
    ])


def sub_actions(lang: str, sub_id: int, token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "cfg_copy"), callback_data=f"sub:link:{sub_id}"),
         InlineKeyboardButton(text=t(lang, "cfg_qr"), callback_data=f"sub:qr:{sub_id}")],
        [InlineKeyboardButton(text=t(lang, "sub_rotate"), callback_data=f"sub:rotate:{sub_id}"),
         InlineKeyboardButton(text="🚫 " + ("لغو اشتراک" if lang == "fa" else "Revoke"),
                              callback_data=f"sub:revoke:{sub_id}")],
        [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="menu:subs")],
    ])


def profile_pick(lang: str, profiles: list[tuple[int, str]], prefix: str = "test") -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=name, callback_data=f"{prefix}:{pid}")] for pid, name in profiles[:10]]
    rows.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_panel(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "adm_users"), callback_data="adm:users"),
         InlineKeyboardButton(text=t(lang, "adm_ippool"), callback_data="adm:ippool")],
        [InlineKeyboardButton(text=t(lang, "adm_proxy"), callback_data="adm:proxy"),
         InlineKeyboardButton(text=t(lang, "adm_settings"), callback_data="adm:settings")],
        [InlineKeyboardButton(text=t(lang, "adm_audit"), callback_data="adm:audit"),
         InlineKeyboardButton(text=t(lang, "adm_broadcast"), callback_data="adm:broadcast")],
        [InlineKeyboardButton(text=t(lang, "adm_scan_now"), callback_data="adm:scan"),
         InlineKeyboardButton(text=t(lang, "adm_backup"), callback_data="adm:backup")],
        [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="menu:main")],
    ])


def admin_user_actions(lang: str, uid: int, suspended: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "adm_user_suspend") if not suspended else t(lang, "adm_user_activate"),
                              callback_data=f"adm:u{'act' if suspended else 'sus'}:{uid}")],
        [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="adm:users")],
    ])


def support_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "support_new_ticket"), callback_data="sup:new"),
         InlineKeyboardButton(text=t(lang, "support_my_tickets"), callback_data="sup:list")],
        [InlineKeyboardButton(text=t(lang, "support_faq"), callback_data="sup:faq")],
        [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="menu:main")],
    ])


def support_categories(lang: str) -> InlineKeyboardMarkup:
    cats = [("connection", "🔌 اتصال" if lang == "fa" else "🔌 Connection"),
            ("cloudflare", "☁️ Cloudflare"),
            ("billing", "💳 " + ("اشتراک" if lang == "fa" else "Subscription")),
            ("general", "💬 " + ("عمومی" if lang == "fa" else "General"))]
    rows = [[InlineKeyboardButton(text=label, callback_data=f"sup:cat:{key}")] for key, label in cats]
    rows.append([InlineKeyboardButton(text=t(lang, "btn_cancel"), callback_data="menu:support")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
