"""Tutorials — 16 bilingual topics, accessible inside Telegram."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.helpers import guard_user, lang_of, rate_ok
from app.bot.i18n import t

router = Router()

TOPICS = [
    ("cf_connect", "اتصال اکانت Cloudflare", "Connect Cloudflare account"),
    ("cf_token", "ساخت API Token", "Create an API token"),
    ("custom_domain", "تنظیم دامنه اختصاصی", "Configure a custom domain"),
    ("vless_create", "ساخت کانفیگ VLESS", "Create a VLESS config"),
    ("trojan_create", "ساخت کانفیگ Trojan", "Create a Trojan config"),
    ("import_android", "امپورت در اندروید", "Import on Android"),
    ("import_ios", "امپورت در iOS", "Import on iOS"),
    ("import_windows", "امپورت در ویندوز", "Import on Windows"),
    ("sub_links", "استفاده از لینک اشتراک", "Using subscription links"),
    ("single_links", "استفاده از لینک تکی", "Using single config links"),
    ("qr_usage", "استفاده از QR code", "Using QR codes"),
    ("proxy_chain", "فعال‌سازی Proxy Chain", "Enable Proxy Chain"),
    ("static_ip", "استفاده از Static IP", "Using a static egress IP"),
    ("quality_test", "تست کیفیت اتصال", "Test connection quality"),
    ("troubleshoot", "عیب‌یابی اتصال", "Troubleshooting"),
    ("faq", "سوالات متداول", "FAQ"),
]

CONTENT = {
    "fa": {
        "cf_connect": "۱. دکمه «اکانت Cloudflare» را بزنید\n۲. «اتصال Cloudflare» را انتخاب کنید\n۳. توکن را طبق راهنما بسازید و بفرستید\n۴. دامنه (Zone) را انتخاب کنید\n\n🔒 توکن رمزنگاری‌شده ذخیره می‌شود.",
        "cf_token": "۱. dash.cloudflare.com → My Profile → API Tokens\n۲. Create Token → قالب Edit zone DNS\n۳. Zone Resources → دامنه خودتان\n۴. Continue → Create → کپی توکن\n\n⚠️ هرگز از Global API Key استفاده نکنید.",
        "custom_domain": "دامنه باید روی Cloudflare باشد. بعد از اتصال اکانت، ربات رکورد DNS لازم را می‌سازد و دامنه برای کانفیگ‌های WebSocket استفاده می‌شود.",
        "vless_create": "🟢 ساخت VPN → انتخاب VLESS → نام پروفایل → دریافت کانفیگ‌ها.\n\nVLESS+REALITY مستقیم روی IP سرور کار می‌کند و نیازی به دامنه ندارد.",
        "trojan_create": "🟢 ساخت VPN → انتخاب Trojan → نام پروفایل.\n\nبدون دامنه، Trojan با self-signed cert ارائه می‌شود (allowInsecure). برای امنیت کامل، دامنه متصل کنید.",
        "import_android": "۱. v2rayNG یا Nekobox را نصب کنید\n۲. از + گزینه Import from clipboard\n۳. لینک کانفیگ را کپی کرده بودید → وارد می‌شود\n۴. اشتراک: Subscription → add → لینک sub را بدهید",
        "import_ios": "۱. Streisand یا Shadowrocket از App Store\n۲. دکمه + → Import from clipboard\n۳. یا از QR code اسکن کنید",
        "import_windows": "۱. Nekoray یا v2rayN\n۲. Server → Import from clipboard\n۳. اشتراک: Subscriptions → Add → لینک sub",
        "sub_links": "لینک اشتراک شامل همه کانفیگ‌های شماست. در کلاینت آن را به‌عنوان Subscription اضافه کنید؛ هر بار به‌روزرسانی، کانفیگ‌های تازه دریافت می‌شود.",
        "single_links": "هر کانفیگ یک لینک جدا دارد؛ می‌توانید فقط همان یکی را در کلاینت اضافه کنید.",
        "qr_usage": "دکمه 🖼 QR تصویر QR همان کانفیگ را می‌فرستد؛ در دستگاه دیگر اسکنش کنید.",
        "proxy_chain": "Proxy Chain ترافیک شما را از یک IP خروجی ثابت عبور می‌دهد. ادمین باید upstream سالم ثبت کرده باشد؛ سپس در ساخت پروفایل فعالش کنید.",
        "static_ip": "Static IP همان IP خروجی اختصاصی است؛ برای سرویس‌هایی که به IP ثابت نیاز دارند مناسب است. سازگاری سرویس‌ها را رعایت کنید.",
        "quality_test": "🔵 تست اتصال → پروفایل را انتخاب کنید. خروجی: وضعیت endpoint، latency و نوع تست.\n\n⚠️ این تست endpoint است؛ تست تونل کامل VPN نیست.",
        "troubleshoot": "۱. تست اتصال بگیرید — کدام endpoint fail است؟\n۲. ساعت و تاریخ دستگاه درست باشد\n۳. کلاینت را آپدیت کنید\n۴. در قطع کامل: از DNS 1.1.1.1 استفاده کنید\n۵. مشکل ادامه داشت: تیکت با دسته «اتصال» بسازید",
        "faq": "س: کانفیگ رایگان است؟ — بستگی به سیاست ادمین دارد.\nس: چند کانفیگ می‌گیرم؟ — تا ۶ کانفیگ مستقل در هر درخواست.\nس: اطلاعات من امن است؟ — توکن‌ها رمزنگاری‌شده ذخیره می‌شوند.",
    },
    "en": {
        "cf_connect": "1. Tap «Cloudflare Account»\n2. Choose «Connect Cloudflare»\n3. Create the token per the guide and send it\n4. Pick your zone\n\n🔒 Stored encrypted.",
        "cf_token": "1. dash.cloudflare.com → My Profile → API Tokens\n2. Create Token → template Edit zone DNS\n3. Zone Resources → your domain\n4. Continue → Create → copy\n\n⚠️ Never use the Global API Key.",
        "custom_domain": "Your domain must be on Cloudflare. After connecting the account, the bot creates required DNS records and the domain is used for WebSocket configs.",
        "vless_create": "🟢 Create VPN → VLESS → profile name → receive configs.\n\nVLESS+REALITY works directly on the server IP — no domain needed.",
        "trojan_create": "🟢 Create VPN → Trojan → profile name.\n\nWithout a domain, Trojan uses a self-signed certificate (allowInsecure). Connect a domain for full security.",
        "import_android": "1. Install v2rayNG or Nekobox\n2. + → Import from clipboard\n3. Paste the copied config link\n4. Subscriptions → add your sub URL",
        "import_ios": "1. Install Streisand or Shadowrocket\n2. + → Import from clipboard\n3. Or scan the QR code",
        "import_windows": "1. Install Nekoray or v2rayN\n2. Server → Import from clipboard\n3. Subscriptions → Add → sub URL",
        "sub_links": "A subscription contains all your configs. Add it as a Subscription in your client; updates deliver fresh endpoints.",
        "single_links": "Each config has its own link; import just that one if you prefer.",
        "qr_usage": "The 🖼 QR button sends a QR image of that config; scan it on another device.",
        "proxy_chain": "Proxy Chain routes traffic through a dedicated static egress IP. An admin must register healthy upstreams; then enable it when creating a profile.",
        "static_ip": "Static IP is your dedicated egress address for services that require a stable source IP. Respect each service's terms.",
        "quality_test": "🔵 Connection Test → pick a profile. Output: endpoint status, latency, check type.\n\n⚠️ Endpoint-level check — not a full tunnel test.",
        "troubleshoot": "1. Run Connection Test — which endpoint fails?\n2. Verify device date/time\n3. Update your client\n4. Total outage: try DNS 1.1.1.1\n5. Still failing: open a «Connection» ticket",
        "faq": "Q: Is it free? — Depends on admin policy.\nQ: How many configs? — Up to 6 independent ones per request.\nQ: Is my data safe? — Tokens are stored encrypted.",
    },
}


def _menu(lang: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=fa if lang == "fa" else en, callback_data=f"tut:{key}")]
            for key, fa, en in TOPICS]
    # 2-column symmetric layout
    grid = [rows[i:i + 2] for i in range(0, len(rows), 2)]
    grid.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=grid)


@router.callback_query(F.data == "menu:tutorials")
async def cb_tutorials(cb: CallbackQuery):
    user = await guard_user(cb)
    if user is None or not rate_ok(user.id):
        await cb.answer()
        return
    lang = lang_of(user)
    await cb.message.edit_text(t(lang, "tutorials_title"), reply_markup=_menu(lang))
    await cb.answer()


@router.callback_query(F.data.startswith("tut:"))
async def cb_tutorial_topic(cb: CallbackQuery):
    user = await guard_user(cb)
    if user is None or not rate_ok(user.id):
        await cb.answer()
        return
    lang = lang_of(user)
    key = cb.data.split(":", 1)[1]
    topic = next((tp for tp in TOPICS if tp[0] == key), None)
    if topic is None:
        await cb.answer()
        return
    body = CONTENT.get(lang, CONTENT["fa"]).get(key, "")
    title = topic[1] if lang == "fa" else topic[2]
    await cb.message.edit_text(t(lang, "tut_placeholder", title=title, body=body),
                               reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                   [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="menu:tutorials")]]))
    await cb.answer()
