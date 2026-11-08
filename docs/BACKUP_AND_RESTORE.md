# Backup & Restore — بکاپ و بازیابی

## Automated
Worker job `backup` runs daily at `BACKUP_SCHEDULE_HOUR` (default 04:30) → `scripts/backup.sh`:
- `newvpn_db_<stamp>.dump` — pg_dump -Fc
- `newvpn_xray_state_<stamp>.tgz` — reality keys + certs
- retention: 14 newest kept

## Manual
```bash
docker compose exec bot /app/scripts/backup.sh     # inside stack
bash scripts/backup.sh                              # on host (needs pg_dump or docker)
```

## Restore
```bash
bash scripts/restore.sh backups/newvpn_db_YYYYMMDD_HHMMSS.dump
```
Confirms with `YES` (destructive). Xray state: extract tgz over `/var/lib/docker/volumes/newvpn_xrayconfig/_data` then `docker compose restart xray`.

## Off-server copies
Mount a host directory into the `backups` volume path or rsync `/var/lib/docker/volumes/newvpn_backups/_data` offsite regularly.
