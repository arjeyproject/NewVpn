# Configuration — پیکربندی

All configuration is environment-driven (`docker-compose.yml` → `.env`). See `.env.example` for the full list.

## Key variables
| var | meaning | default |
|---|---|---|
| BOT_TOKEN | @BotFather token | — (required) |
| ADMIN_TELEGRAM_IDS | comma-separated numeric IDs | — |
| ENCRYPTION_KEY | Fernet key; encrypts CF tokens & proxy creds | generated |
| SERVER_PUBLIC_IP | origin IP in generated configs | auto |
| SUBSCRIPTION_BASE_URL | public sub base; empty → http://IP:8080 | empty |
| CONFIGS_PER_PROFILE | configs per request (max) | 6 |
| CONFIG_EXPIRY_DAYS | profile lifetime | 30 |
| IP_SCAN_CRON | scanner schedule | `0 3,15 * * *` |
| IP_SCAN_SAMPLE_PER_RANGE | sampled IPs per CIDR | 40 |
| IP_SCAN_CONCURRENCY | scanner concurrency bound | 200 |
| REALITY_DEST / REALITY_SERVER_NAME | REALITY camouflage target | samsung |

Apply changes: edit `.env` → `docker compose up -d` (recreates affected containers). Sensitive values are never logged.
