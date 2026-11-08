# Deployment — استقرار

## Stack
Docker Compose: `db` + `bot` + `api` + `worker` + `migrate` + `xray` (supervisor loop over the shared config volume).

## Restart policy
All services run with `restart: unless-stopped`. The worker re-marks interrupted jobs as failed on boot, so unfinished scans/rotations are recovered safely without duplicate subscriptions.

## Update
```bash
bash scripts/update.sh   # git pull → build → migrate → up -d
```

## Server checklist (prompt §18)
1. Inspect server / installed software  2. Backup (`scripts/backup.sh`)
3. Install missing deps (install.sh)    4. Configure `.env`
5. `docker compose run --rm migrate`    6. `docker compose up -d`
7. `bash scripts/healthcheck.sh`        8. verify Telegram bot replies

## First-boot flow
db healthy → migrate creates schema → bot standby (waits token) → api serves /health → worker schedules 8 jobs → xray supervisor waits for the app-generated config.json.
