# Troubleshooting — عیب‌یابی

## Bot does not respond
1. `docker compose logs bot | tail -20` → "BOT_TOKEN is not configured" means set token in `.env` then `docker compose up -d bot`.
2. Wrong token → bot exits; container restarts; fix token.
3. `bash scripts/healthcheck.sh` for the full status.

## No configs generated / create_failed
- Endpoints failed live validation (skipped list is shown). Check ports 443/8080/8443/8444 open on the host firewall (`ufw status`).
- `docker compose logs bot | grep -i provision`.

## Xray not running
- Config missing: `docker compose exec bot ls /etc/newvpn/xray` (config.json must exist after first provisioning).
- Binary missing: check `/opt/newvpn/xray/xray` exists (install.sh fetched it).
- Supervisor logs: `docker compose logs xray`.

## Trojan flagged insecure
Expected without a domain (`allowInsecure=1`, self-signed cert). Connect a Cloudflare domain for proper TLS.

## IP pool empty
Scanner runs 03:00/15:00; trigger manual scan from admin panel. If sample ranges unreachable (network restrictions), add `EXTRA_CANDIDATE_RANGES`.

## Subscription 404
Token revoked/expired → regenerate from 🟢 اشتراک‌های من → rotate.

## Restore from backup
`bash scripts/restore.sh backups/newvpn_db_<stamp>.dump`
