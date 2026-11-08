# Cloudflare Setup — اتصال Cloudflare

## User flow (in bot)
Connect Cloudflare → step-by-step token guide → token submitted (message auto-deleted from chat!) → verified against `/user/tokens/verify` → zones listed → user picks a zone → DNS edit permission proved by listing records → account ACTIVE.

## Token policy (فارسی)
- فقط API Token؛ Global API Key به‌صورت طراحی‌شده رد می‌شود.
- کمترین دسترسی لازم: قالب **Edit zone DNS** روی دامنه‌ی خودتان.
- توکن با Fernet رمزنگاری و فقط ciphertext در DB ذخیره می‌شود؛ در پیام‌ها/لاگ‌ها هرگز ظاهر نمی‌شود.
- قطع اتصال → توکن از منطق فعال حذف و status=revoked می‌شود.

## What the platform automates
- Zone validation (status + dns_records:edit proof)
- Domain registration into the provisioning pool
- DNS record creation for WebSocket entries when a domain is connected (API: POST /zones/{id}/dns_records)

## What Cloudflare cannot do (honest limits)
Workers/Pages do not provide arbitrary TCP forwarding or dedicated VPN egress IPs; CF is used as the WebSocket/edge layer only, with a real Xray origin.
