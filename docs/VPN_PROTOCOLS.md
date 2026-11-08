# VPN Protocols — پروتکل‌ها

## Deployed transports
| # | protocol | transport | port | TLS | domain needed |
|---|---|---|---|---|---|
| 1 | VLESS | TCP + REALITY | 443 | REALITY (uTLS chrome fp, flow xtls-rprx-vision) | no |
| 2 | VLESS | WebSocket | 8080 | none (direct) | no |
| 3 | Trojan | TCP+TLS | 8443 | self-signed (allowInsecure=1) | no |
| 4 | Trojan | WS+TLS | 8444 | self-signed (allowInsecure=1) | no |
| 5 | VLESS | WS+TLS via CF edge | 443 | edge TLS, SNI/Host = user domain | yes |
| 6 | Trojan | WS+TLS via CF edge | 443 | edge TLS | yes |

## Credentials
Every config has its own UUID (vless) or 32-byte urlsafe password (trojan). REALITY keys are generated per server with `cryptography`'s X25519 and persisted in `/etc/newvpn/xray/reality.json` (chmod 600).

## Validation (before delivery)
TCP connect → TLS handshake (SNI honored) → WS upgrade probe (101/400/426 counts as alive-behind-edge). Latency is measured during the strongest available check. ICMP is never presented as a VPN test.

## Client compatibility
v2rayNG · Nekobox/Nekoray · Streisand · Shadowrocket · v2rayN — all standard share-link parameters (pbk/sid/fp/flow/path/host).
