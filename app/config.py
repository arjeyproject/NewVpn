"""NewVpn application configuration — everything configurable via environment variables."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Core ---
    app_name: str = "NewVpn"
    debug: bool = False
    timezone: str = "Asia/Tehran"

    # --- Database ---
    database_url: str = "postgresql+asyncpg://newvpn:newvpn@db:5432/newvpn"
    db_pool_size: int = 10

    # --- Telegram ---
    bot_token: str = ""  # from @BotFather
    admin_telegram_ids: str = ""  # comma separated numeric IDs
    default_language: str = "fa"
    bot_display_name: str = "AutoVless"  # branding shown in texts & Telegram profile
    support_handle: str = "@irezafattahi"  # support contact (without https:// prefix)
    channel_handle: str = "@AutoVless"  # official channel

    # --- Security ---
    encryption_key: str = ""  # Fernet key (openssl rand -base64 32) — encrypts CF tokens & proxy creds

    # --- Subscription API ---
    sub_api_host: str = "0.0.0.0"
    sub_api_port: int = 8080
    subscription_base_url: str = ""  # e.g. https://vpn.example.com — empty => http://SERVER_IP:8080
    sub_request_rate_limit: int = 30  # requests per minute per token

    # --- Server / VPN backend ---
    server_public_ip: str = ""  # auto-detected if empty
    xray_config_dir: str = "/etc/newvpn/xray"
    xray_validation_host: str = "xray"  # compose-internal DNS name of the xray container
    xray_reality_port: int = 443
    xray_ws_port: int = 8080
    xray_trojan_port: int = 8443
    xray_chain_port_base: int = 20000
    reality_dest: str = "www.samsung.com:443"
    reality_server_name: str = "www.samsung.com"
    reality_short_ids: str = ""  # comma separated hex; auto-generated if empty
    configs_per_profile: int = 6
    config_expiry_days: int = 30
    ws_path_prefix: str = "/newvpn"

    # --- IP scanner ---
    ip_scan_cron: str = "0 3,15 * * *"  # twice daily 03:00 / 15:00 server time
    ip_scan_sample_per_range: int = 40
    ip_scan_concurrency: int = 200
    ip_scan_ports: str = "443"  # comma separated
    ip_scan_timeout: float = 3.0
    ip_min_quality_score: int = 40
    candidate_ranges_url: str = "https://www.cloudflare.com/ips-v4"
    extra_candidate_ranges: str = ""  # comma separated CIDRs

    # --- Proxy chain ---
    proxy_health_interval_minutes: int = 10
    proxy_max_users_default: int = 5

    # --- Background jobs ---
    endpoint_monitor_interval_minutes: int = 5
    sub_expiry_check_minutes: int = 30
    cleanup_interval_hours: int = 24
    backup_schedule_hour: int = 4
    alert_cooldown_minutes: int = 30

    # --- Logging ---
    log_level: str = "INFO"

    @property
    def admin_ids(self) -> list[int]:
        return [int(x.strip()) for x in self.admin_telegram_ids.split(",") if x.strip().isdigit()]

    @property
    def scanner_ports(self) -> list[int]:
        return [int(p) for p in self.ip_scan_ports.split(",") if p.strip().isdigit()]

    @property
    def extra_ranges(self) -> list[str]:
        return [r.strip() for r in self.extra_candidate_ranges.split(",") if r.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
