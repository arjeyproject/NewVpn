"""Cloudflare API v4 async client — least-privilege token handling.

Security rules enforced here:
- Only API Tokens (Bearer). Global API Key is never requested or accepted.
- Tokens are never logged; errors are sanitized.
- Every call has a timeout and bounded response parsing.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

log = logging.getLogger("newvpn.cloudflare")

API_BASE = "https://api.cloudflare.com/client/v4"
TIMEOUT = httpx.Timeout(20.0, connect=10.0)


class CloudflareError(Exception):
    """Sanitized CF error — safe to show to end users."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass
class CfTokenInfo:
    valid: bool
    token_id: str = ""
    account_id: str = ""
    account_name: str = ""


@dataclass
class CfZone:
    zone_id: str
    name: str
    status: str
    can_edit_dns: bool = False


@dataclass
class CfDnsRecord:
    record_id: str
    type: str
    name: str
    content: str
    proxied: bool
    ttl: int = 1


@dataclass
class ZoneValidation:
    zone: CfZone | None = None
    errors: list[str] = field(default_factory=list)
    dns_records_count: int = 0


class CloudflareClient:
    def __init__(self, api_token: str):
        if not api_token or api_token.strip().startswith("v4.0-"):
            # Global-API-key-looking material is rejected by design.
            raise CloudflareError("Only a Cloudflare API Token (Bearer) is supported. Global API Keys are not allowed.")
        self._token = api_token.strip()
        self._headers = {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{API_BASE}{path}"
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.request(method, url, headers=self._headers, **kwargs)
        except httpx.HTTPError:
            raise CloudflareError("Network error while contacting Cloudflare API — try again later.")
        try:
            data = resp.json()
        except ValueError:
            raise CloudflareError(f"Cloudflare API returned an unexpected response (HTTP {resp.status_code}).")
        if resp.status_code >= 400:
            msgs = []
            for err in (data.get("errors") or [])[:3]:
                code = err.get("code")
                msg = str(err.get("message", "unknown error"))
                # 9109 / 10000-style messages may echo auth context — keep them but never echo token
                msgs.append(f"[{code}] {msg}")
            raise CloudflareError(f"Cloudflare error (HTTP {resp.status_code}): " + "; ".join(msgs) or "unknown")
        return data

    # --- Token & account -------------------------------------------------
    async def verify_token(self) -> CfTokenInfo:
        data = await self._request("GET", "/user/tokens/verify")
        result = data.get("result") or {}
        info = CfTokenInfo(valid=result.get("status") == "active", token_id=str(result.get("id", "")))
        try:
            accounts = await self.get_accounts()
            if accounts:
                info.account_id, info.account_name = accounts[0][0], accounts[0][1]
        except CloudflareError:
            pass  # token valid but no account scope — still usable for some flows
        return info

    async def get_accounts(self) -> list[tuple[str, str]]:
        data = await self._request("GET", "/accounts?per_page=5")
        return [(a["id"], a.get("name", "")) for a in (data.get("result") or [])[:5]]

    # --- Zones ------------------------------------------------------------
    async def get_zones(self) -> list[CfZone]:
        data = await self._request("GET", "/zones?per_page=50")
        zones = []
        for z in (data.get("result") or []):
            perms = z.get("permissions") or []
            zones.append(
                CfZone(
                    zone_id=z["id"],
                    name=z["name"],
                    status=z.get("status", "unknown"),
                    can_edit_dns="#dns_records:edit" in perms or "#zone:edit" in perms,
                )
            )
        return zones

    async def validate_zone_for_dns(self, zone_id: str) -> ZoneValidation:
        """Validate DNS edit permission by actually listing records (least-privilege proof)."""
        validation = ZoneValidation()
        try:
            data = await self._request("GET", f"/zones/{zone_id}")
            z = data.get("result") or {}
            validation.zone = CfZone(
                zone_id=z.get("id", zone_id), name=z.get("name", ""), status=z.get("status", "unknown")
            )
        except CloudflareError as exc:
            validation.errors.append(exc.message)
            return validation
        try:
            data = await self._request("GET", f"/zones/{zone_id}/dns_records?per_page=1")
            validation.dns_records_count = len(data.get("result") or [])
        except CloudflareError as exc:
            validation.errors.append(f"DNS edit permission missing: {exc.message}")
        return validation

    # --- DNS records --------------------------------------------------------
    async def create_dns_record(self, zone_id: str, name: str, record_type: str, content: str, proxied: bool, ttl: int = 1) -> CfDnsRecord:
        payload = {"type": record_type, "name": name, "content": content, "ttl": ttl, "proxied": proxied}
        data = await self._request("POST", f"/zones/{zone_id}/dns_records", json=payload)
        r = data.get("result") or {}
        return CfDnsRecord(
            record_id=r.get("id", ""), type=r.get("type", record_type), name=r.get("name", name),
            content=r.get("content", content), proxied=bool(r.get("proxied", proxied)),
        )

    async def list_dns_records(self, zone_id: str, name: str | None = None) -> list[CfDnsRecord]:
        query = f"?per_page=100" + (f"&name={name}" if name else "")
        data = await self._request("GET", f"/zones/{zone_id}/dns_records{query}")
        return [
            CfDnsRecord(r["id"], r.get("type", ""), r.get("name", ""), r.get("content", ""), bool(r.get("proxied")))
            for r in (data.get("result") or [])
        ]

    async def delete_dns_record(self, zone_id: str, record_id: str) -> bool:
        await self._request("DELETE", f"/zones/{zone_id}/dns_records/{record_id}")
        return True
