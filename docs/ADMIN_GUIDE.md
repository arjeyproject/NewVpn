# Admin Guide — راهنمای ادمین

## Access
Set your numeric Telegram ID in `ADMIN_TELEGRAM_IDS`. `/start` shows your ID. The admin button (🛠 پنل ادمین) appears only for admins; every callback is re-checked server-side.

## Dashboard
Users (total/active) · active configs · active subs · CF accounts · healthy IPs · healthy proxies · running jobs.

## Sections
- **Users**: search by ID/username, suspend/activate (audit-logged).
- **IP pool**: live stats + top 10 by score, manual scan trigger.
- **Proxy**: inventory with egress IPs and health.
- **Settings**: env-driven values (view) — edit `.env` + restart to apply.
- **Audit log**: last 15 administrative actions (suspensions, broadcasts, scans).
- **Broadcast**: message to all active users (delivery counters recorded).
- **Backup now**: instant DB dump + xray state tarball.

## Operations
```bash
bash scripts/healthcheck.sh       # full health
docker compose logs -f bot        # bot logs
docker compose restart bot        # restart bot only
```
