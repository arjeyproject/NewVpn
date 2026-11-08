# Installation — نصب

## Prerequisites
- Ubuntu 22.04/24.04 (Debian 12 works), 1 vCPU / 1 GB RAM minimum
- Root access, open ports: 22 (SSH), 443, 8080, 8443, 8444, 8080/tcp API, 20000–20050

## Steps (فارسی)
1. `git clone https://github.com/arjeyproject/NewVpn.git && cd NewVpn`
2. `sudo bash scripts/install.sh` — نصب Docker، دانلود Xray (با میرورهای جایگزین)، ساخت `.env` با کلیدهای تصادفی، اجرای migration و بالا آوردن سرویس‌ها
3. `nano .env` → مقدار `BOT_TOKEN` (از @BotFather) و `ADMIN_TELEGRAM_IDS` را بگذارید
4. `docker compose up -d bot`
5. تست: `bash scripts/healthcheck.sh`

## Services
| service | role | port |
|---|---|---|
| db | PostgreSQL 16 | internal |
| bot | Telegram bot | — |
| api | subscription API | 8080 |
| worker | scheduler/jobs | — |
| migrate | one-shot alembic | — |
| xray | VPN backend | 443/8080/8443/8444/20000+ |

The bot container stays in standby (retry every 60s) until BOT_TOKEN is set — it never crash-loops.
