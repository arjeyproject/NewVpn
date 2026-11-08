# Clean IP Pool — استخر IP سالم

## Model
`ip_inventory` (address+port unique) with provider/ASN/latency/success-fail counters/quality score/health class + `ip_profile_results` per network profile.

## Scanner
- Sources: Cloudflare published v4 ranges (configurable) + extra CIDRs; **no unowned ranges are scanned**.
- Sampling: N IPs per CIDR (default 40) → bounded TCP:443 probes (default concurrency 200, timeout 3s).
- Schedule: twice daily (`IP_SCAN_CRON`) + manual from admin panel.
- Health: excellent ≥85 / good ≥65 / average ≥40 / unhealthy <40; repeated failures decay score 30/check and purge at <10 after 3 fails.

## Scoring
latency → base score (≤80ms=100, ≤150=85, ≤300=65, ≤600=45, else 25), smoothed by averaging with previous score for stability.

## Operator profiles
`ip_profile_results` stores per-profile measurements (mobile/fixed profiles configurable) — universal compatibility is never claimed without real results.
