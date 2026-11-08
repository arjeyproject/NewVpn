# Proxy Chain & Static Egress IP — زنجیره پروکسی

## What it does
Routes a user's VPN traffic through an upstream SOCKS5/HTTP proxy with a stable public egress IP. Useful for legitimate services that require a consistent source IP.

## How it is implemented
- Admin registers upstreams (host/port/protocol/credentials — encrypted at rest).
- Health checker connects **through** the proxy to `api.ipify.org` and records the real egress IP; stability is tracked across checks (egress_stable).
- Chained profiles get a **dedicated Xray inbound** (port 20000+profile) routed to `out-chain-{profile}` (socks/http outbound with auth).
- Users see assignment status; admins see inventory, usage and health.

## Honest limits
- Cloudflare does not provide dedicated static egress IPs — a real egress provider/server is required; the engine does the rest.
- No third-party service access is promised; compliance with each provider's terms is the operator's responsibility.

## Management
- Add/remove: admin panel → Proxy management (or `scripts/add_proxy.py`)
- Checks: every 10 min (`proxy_health_interval_minutes`)
- Abuse control: per-proxy max_users, per-user assignment, revocation.
