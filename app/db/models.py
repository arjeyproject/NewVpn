"""SQLAlchemy 2.0 models — NewVpn persistent storage."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)  # telegram id
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    language: Mapped[str] = mapped_column(String(2), default="fa")
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|suspended|banned
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    max_configs: Mapped[int] = mapped_column(Integer, default=30)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    profiles: Mapped[list[VpnProfile]] = relationship(back_populates="user")
    cf_accounts: Mapped[list[CloudflareAccount]] = relationship(back_populates="user")


class CloudflareAccount(Base):
    __tablename__ = "cloudflare_accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(128), default="cloudflare")
    account_id_cf: Mapped[str | None] = mapped_column(String(64))
    account_name: Mapped[str | None] = mapped_column(String(256))
    api_token_encrypted: Mapped[str] = mapped_column(Text)  # Fernet ciphertext — never plaintext
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|active|invalid|revoked
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="cf_accounts")
    zones: Mapped[list[CloudflareZone]] = relationship(back_populates="account", cascade="all, delete-orphan")


class CloudflareZone(Base):
    __tablename__ = "cloudflare_zones"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("cloudflare_accounts.id", ondelete="CASCADE"))
    zone_id_cf: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(32), default="active")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped[CloudflareAccount] = relationship(back_populates="zones")


class Domain(Base):
    """Domains usable for provisioning / subscription endpoints."""
    __tablename__ = "domains"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    zone_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("cloudflare_zones.id", ondelete="SET NULL"))
    owner_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(256), unique=True)
    purpose: Mapped[str] = mapped_column(String(16), default="entry")  # entry|sub
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|disabled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VpnServer(Base):
    """VPN origin servers running our Xray backend."""
    __tablename__ = "vpn_servers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    host: Mapped[str] = mapped_column(String(256))
    country: Mapped[str] = mapped_column(String(64), default="")
    provider: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(16), default="active")
    last_health_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_health_status: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VpnProfile(Base):
    """One provisioning request: groups up to N configs + a subscription."""
    __tablename__ = "vpn_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(128))
    protocol: Mapped[str] = mapped_column(String(16), default="vless")  # vless|trojan|mixed
    transport: Mapped[str] = mapped_column(String(16), default="auto")
    domain_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("domains.id", ondelete="SET NULL"))
    proxy_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|expired|revoked
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="profiles")
    configs: Mapped[list[VpnConfig]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    subscription: Mapped[Subscription | None] = relationship(back_populates="profile", uselist=False, cascade="all, delete-orphan")


class VpnConfig(Base):
    """A single generated VPN configuration (endpoint + credential)."""
    __tablename__ = "vpn_configs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(Integer, ForeignKey("vpn_profiles.id", ondelete="CASCADE"))
    protocol: Mapped[str] = mapped_column(String(16))  # vless|trojan
    transport: Mapped[str] = mapped_column(String(16))  # reality|ws|grpc|trojan-tls|trojan-ws
    address: Mapped[str] = mapped_column(String(256))  # connect address (IP or domain)
    port: Mapped[int] = mapped_column(Integer)
    sni: Mapped[str | None] = mapped_column(String(256))
    host_header: Mapped[str | None] = mapped_column(String(256))
    path: Mapped[str | None] = mapped_column(String(256))
    credential: Mapped[str] = mapped_column(String(256))  # uuid or trojan password (client-facing)
    internal_tag: Mapped[str | None] = mapped_column(String(64))  # xray client email tag
    flow: Mapped[str | None] = mapped_column(String(64))
    fingerprint: Mapped[str | None] = mapped_column(String(32), default="chrome")
    name: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|expired|revoked|unhealthy
    proxied_via_cf: Mapped[bool] = mapped_column(Boolean, default=False)
    proxy_assignment_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("proxy_assignments.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_check_status: Mapped[str | None] = mapped_column(String(16))
    last_latency_ms: Mapped[int | None] = mapped_column(Integer)

    profile: Mapped[VpnProfile] = relationship(back_populates="configs")
    __table_args__ = (Index("ix_configs_profile_status", "profile_id", "status"),)


class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # urlsafe secret — no DB ids exposed
    profile_id: Mapped[int] = mapped_column(Integer, ForeignKey("vpn_profiles.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|revoked|expired
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rotated_from: Mapped[str | None] = mapped_column(String(64))

    profile: Mapped[VpnProfile] = relationship(back_populates="subscription")


class IpInventory(Base):
    __tablename__ = "ip_inventory"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    address: Mapped[str] = mapped_column(String(64))
    port: Mapped[int] = mapped_column(Integer, default=443)
    hostname: Mapped[str | None] = mapped_column(String(256))
    provider: Mapped[str | None] = mapped_column(String(128))
    region: Mapped[str | None] = mapped_column(String(64))
    asn: Mapped[str | None] = mapped_column(String(32))
    country: Mapped[str | None] = mapped_column(String(8))
    tls_status: Mapped[str | None] = mapped_column(String(16))
    ws_compatible: Mapped[bool | None] = mapped_column(Boolean)
    tcp_connect: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    packet_loss: Mapped[float | None] = mapped_column(Float)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    health_status: Mapped[str] = mapped_column(String(16), default="unknown")  # excellent|good|average|unhealthy
    quality_score: Mapped[int] = mapped_column(Integer, default=0)  # 0..100
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_scan_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("address", "port", name="uq_ip_addr_port"),)


class IpScanHistory(Base):
    __tablename__ = "ip_scan_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trigger: Mapped[str] = mapped_column(String(16), default="scheduled")  # scheduled|manual
    network_profile: Mapped[str] = mapped_column(String(64), default="default")
    total_checked: Mapped[int] = mapped_column(Integer, default=0)
    healthy: Mapped[int] = mapped_column(Integer, default=0)
    unhealthy: Mapped[int] = mapped_column(Integer, default=0)
    new_entries: Mapped[int] = mapped_column(Integer, default=0)
    removed: Mapped[int] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|completed|failed
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IpProfileResult(Base):
    """Per-network-profile measurement results (operator compatibility)."""
    __tablename__ = "ip_profile_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ip_id: Mapped[int] = mapped_column(Integer, ForeignKey("ip_inventory.id", ondelete="CASCADE"))
    network_profile: Mapped[str] = mapped_column(String(64))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (Index("ix_ip_profile_results_ip", "ip_id", "network_profile"),)


class ProxyInventory(Base):
    __tablename__ = "proxy_inventory"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    protocol: Mapped[str] = mapped_column(String(16), default="socks5")  # socks5|http
    host: Mapped[str] = mapped_column(String(256))
    port: Mapped[int] = mapped_column(Integer)
    username_encrypted: Mapped[str | None] = mapped_column(Text)
    password_encrypted: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(String(8))
    region: Mapped[str | None] = mapped_column(String(64))
    provider: Mapped[str | None] = mapped_column(String(128))
    egress_ip: Mapped[str | None] = mapped_column(String(64))
    egress_stable: Mapped[bool | None] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(16), default="checking")  # healthy|unhealthy|checking|disabled
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_egress_ip: Mapped[str | None] = mapped_column(String(64))
    max_users: Mapped[int] = mapped_column(Integer, default=5)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProxyAssignment(Base):
    __tablename__ = "proxy_assignments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    proxy_id: Mapped[int] = mapped_column(Integer, ForeignKey("proxy_inventory.id", ondelete="CASCADE"))
    config_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("vpn_configs.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|revoked
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SupportTicket(Base):
    __tablename__ = "support_tickets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(32), default="general")
    subject: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(16), default="open")  # open|answered|closed
    priority: Mapped[str] = mapped_column(String(16), default="normal")  # low|normal|high
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    messages: Mapped[list[TicketMessage]] = relationship(back_populates="ticket", cascade="all, delete-orphan")


class TicketMessage(Base):
    __tablename__ = "ticket_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(Integer, ForeignKey("support_tickets.id", ondelete="CASCADE"))
    sender: Mapped[str] = mapped_column(String(8))  # user|admin
    sender_id: Mapped[int | None] = mapped_column(BigInteger)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ticket: Mapped[SupportTicket] = relationship(back_populates="messages")


class BackgroundJob(Base):
    __tablename__ = "background_jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|completed|failed
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_jobs_name_status", "name", "status"),)


class SystemSetting(Base):
    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_id: Mapped[int] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserActivity(Base):
    __tablename__ = "user_activity"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    action: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MonitorSnapshot(Base):
    """Periodic system metrics for charts and alerting."""
    __tablename__ = "monitor_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cpu_percent: Mapped[float] = mapped_column(Float, default=0)
    mem_percent: Mapped[float] = mapped_column(Float, default=0)
    disk_percent: Mapped[float] = mapped_column(Float, default=0)
    users_total: Mapped[int] = mapped_column(Integer, default=0)
    configs_active: Mapped[int] = mapped_column(Integer, default=0)
    subs_active: Mapped[int] = mapped_column(Integer, default=0)
    ips_healthy: Mapped[int] = mapped_column(Integer, default=0)
    proxies_healthy: Mapped[int] = mapped_column(Integer, default=0)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
