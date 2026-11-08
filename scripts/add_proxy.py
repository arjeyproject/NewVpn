"""Admin utility: add a proxy-chain upstream.
Usage: python scripts/add_proxy.py <name> <socks5|http> <host> <port> [user] [pass]
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import select  # noqa: E402

from app.db.engine import SessionFactory  # noqa: E402
from app.db.models import ProxyInventory  # noqa: E402
from app.proxy.chain import verify_proxy  # noqa: E402
from app.security import crypto  # noqa: E402


async def main(argv: list[str]) -> int:
    if len(argv) < 5:
        print(__doc__)
        return 1
    name, protocol, host, port = argv[1], argv[2], argv[3], int(argv[4])
    user = argv[5] if len(argv) > 5 else None
    password = argv[6] if len(argv) > 6 else None
    async with SessionFactory() as session:
        exists = (await session.execute(
            select(ProxyInventory).where(ProxyInventory.host == host, ProxyInventory.port == port)
        )).scalar_one_or_none()
        if exists:
            print(f"proxy {host}:{port} already exists as #{exists.id}")
            return 1
        p = ProxyInventory(
            name=name[:64], protocol=protocol if protocol in ("socks5", "http") else "socks5",
            host=host[:128], port=port, max_users=5, status="checking",
        )
        if user and password:
            p.username_encrypted = crypto.encrypt_secret(user)
            p.password_encrypted = crypto.encrypt_secret(password)
        session.add(p)
        await session.flush()
        await verify_proxy(p)
        await session.commit()
        print(f"proxy #{p.id} '{p.name}' status={p.status} egress={p.egress_ip or '—'} latency={p.latency_ms or '—'}ms")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
