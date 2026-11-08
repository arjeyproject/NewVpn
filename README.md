# NewVpn 🚀

**Production-grade Telegram VPN platform powered by a real Xray backend — with Cloudflare Edge integration, clean IP pool, proxy chain and subscriptions.**

فارسی | English documentation below.

---

## فارسی

نیو‌وی‌پی‌ان یک پلتفرم کامل ارائه سرویس VPN از طریق تلگرام است: کاربر با اتصال اکانت Cloudflare، انتخاب پروتکل و دریافت تا **۶ کانفیگ مستقلِ اعتبارسنجی‌شده** به‌همراه **لینک اشتراک** و QR code سرویس خود را دریافت می‌کند.

### اجزای سیستم

| جزء | شرح |
|---|---|
| Telegram Bot | دوزبانه (fa/en)، منوی کامل، پنل ادمین، آموزش، پشتیبانی |
| VPN Provisioning | VLESS+REALITY / VLESS+WS / Trojan+TLS / Trojan+WS |
| Cloudflare Engine | اتصال امن توکن، بررسی Zone، ساخت رکورد DNS |
| Clean IP Pool | اسکن ۲ بار در شبانه‌روز، امتیازدهی کیفیت، حذف ناسالم‌ها |
| Proxy Chain | SOCKS5/HTTP upstream با تأیید واقعی IP خروجی |
| Subscription API | توکن امن، rotate/revoke، هدر subscription-userinfo |
| Worker | ۸ کار پس‌زمینه‌ای با قفل دیتابیس و بازیابی پس از ری‌استارت |
| Monitoring | snapshotهای منابع، هشدار ادمین، /health |

### راه‌اندازی سریع روی سرور

```bash
git clone https://github.com/arjeyproject/NewVpn.git && cd NewVpn
sudo bash scripts/install.sh          # docker + xray + .env + migrate + up
nano .env                             # BOT_TOKEN و ADMIN_TELEGRAM_IDS را تنظیم کنید
docker compose up -d bot
```

سپس ربات را در تلگرام باز کنید و `/start` بزنید — ایدی عددی نمایش‌داده‌شده را در `ADMIN_TELEGRAM_IDS` قرار دهید.

### پروتکل‌ها و کانال‌های واقعی

- **VLESS + REALITY** روی پورت ۴۴۳ (بدون نیاز به دامنه)
- **VLESS + WebSocket** روی پورت ۸۰۸۰
- **Trojan + TLS** روی ۸۴۴۳ (self-signed بدون دامنه)
- **Trojan + WS+TLS** روی ۸۴۴۴
- با اتصال دامنه‌ی Cloudflare: کانفیگ‌های **CF-fronted** روی Clean IPهای استخر

> تعداد کانفیگ‌های تحویلی = تعداد endpointهای واقعاً سالم؛ هرگز عدد ساختگی اعلام نمی‌شود.

---

## English

NewVpn is a complete VPN service delivery platform on Telegram: users connect their Cloudflare account, pick a protocol, and receive up to **six independently validated configurations** with a **subscription URL** and QR codes.

### Components

Telegram Bot (fa/en, admin dashboard, tutorials, tickets) · VPN Provisioning (VLESS+REALITY/WS, Trojan+TLS/WS via Xray-core) · Cloudflare Engine (least-privilege tokens, zones, DNS automation) · Clean IP Pool (2× daily scans, quality scoring) · Proxy Chain (SOCKS5/HTTP upstreams with real egress verification) · Subscription API (secure tokens, rotation, revocation) · Background Worker (8 jobs, DB-locked, restart-safe) · Monitoring (snapshots, admin alerts, /health).

### Quick start

```bash
git clone https://github.com/arjeyproject/NewVpn.git && cd NewVpn
sudo bash scripts/install.sh
nano .env     # set BOT_TOKEN + ADMIN_TELEGRAM_IDS
docker compose up -d bot
```

### Honest engineering notes

- Telegram inline buttons have **no native color API** (verified against core.telegram.org/bots/api) — color semantics are expressed with 🟢/🔵/🔴 emoji prefixes.
- Cloudflare Workers/Pages cannot do arbitrary TCP forwarding — they are not advertised as VPN transports here.
- Without a connected domain, Trojan uses a self-signed certificate (`allowInsecure=1`) — clearly labeled; connecting a domain is recommended.
- Configs are only delivered after live TCP/TLS/WS validation; failed endpoints are reported, never faked.

Full docs: [docs/](docs/) — INSTALL, DEPLOYMENT, CONFIGURATION, CLOUDFLARE_SETUP, VPN_PROTOCOLS, IP_POOL, PROXY_CHAIN, ADMIN_GUIDE, USER_GUIDE, SECURITY, TROUBLESHOOTING, BACKUP_AND_RESTORE.

## License

Private project — all rights reserved by the repository owner.
