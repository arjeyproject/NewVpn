# Security — امنیت

## Secrets
- Cloudflare tokens & proxy credentials: **Fernet-encrypted** at rest (ENCRYPTION_KEY). Plaintext never in DB, logs, or Telegram messages.
- Bot token submission flow deletes the user's message from chat immediately.
- `.env` chmod 600; `.gitignore` excludes it; docs contain no real secrets.

## Access control
- Admin routes verify `ADMIN_TELEGRAM_IDS` **per callback**, not just UI visibility.
- Users can only touch their own configs/subscriptions/CF accounts (ownership checks on every handler).
- Subscription URLs carry opaque urlsafe tokens (24 bytes) — no DB ids, rotatable, revocable.

## Network & abuse
- Xray blocks private-range egress; chained profiles are isolated per-port.
- Rate limiting: 30 req/min per subscription token; callback flood gate in bot.
- Parameterized SQL only (SQLAlchemy); inputs validated/length-capped.

## Ops
- Audit log for administrative actions (never logs secrets).
- Daily automated DB backup (14-day retention) + xray state backup.
- Alerts to admins with cooldown: service failures, IP pool depletion, CF auth failures, failed jobs.
