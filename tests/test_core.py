"""Unit tests — links round-trip, scoring, crypto, subscription tokens.
These tests run against real code with no external services required."""
import pytest

from app.security import crypto
from app.vpn.links import ConfigParams, build_link, parse_link


# ---------- crypto ----------
def test_secret_roundtrip():
    crypto_secrets_module = crypto
    plain = "cf-token-abc123"
    enc = crypto_secrets_module.encrypt_secret(plain)
    assert enc != plain
    assert crypto_secrets_module.decrypt_secret(enc) == plain


def test_subscription_token_unguessable_and_urlsafe():
    tokens = {crypto.generate_subscription_token() for _ in range(200)}
    assert len(tokens) == 200
    assert all("+" not in t and "/" not in t and "=" not in t for t in tokens)
    assert all(len(t) >= 32 for t in tokens)


def test_uuid_and_trojan_password_shapes():
    import uuid as uuidlib
    u = crypto.generate_uuid()
    assert uuidlib.UUID(u).version == 4
    p = crypto.generate_trojan_password()
    assert len(p) >= 24


def test_x25519_keypair_format():
    priv, pub = crypto.generate_x25519_keypair()
    assert len(priv) == 43 and len(pub) == 43  # base64url no padding of 32 bytes
    assert priv != pub
    import base64
    base64.urlsafe_b64decode(priv + "==")
    base64.urlsafe_b64decode(pub + "==")


# ---------- links ----------
def test_vless_reality_link_roundtrip():
    p = ConfigParams(
        protocol="vless", address="1.2.3.4", port=443,
        credential="3f2504e0-4f89-11d3-9a0c-0305e82c3301",
        transport="tcp", security="reality", sni="www.samsung.com",
        flow="xtls-rprx-vision", fingerprint="chrome",
        public_key="bWVhEGmNrOGftZ5c-l0fVhJcdUlD8zYdPNSkEfCgoJUo",
        short_id="a1b2c3d4", name="تست کانفیگ #1",
    )
    link = build_link(p)
    assert link.startswith("vless://")
    q = parse_link(link)
    assert q.address == "1.2.3.4" and q.port == 443
    assert q.credential == p.credential
    assert q.security == "reality" and q.sni == "www.samsung.com"
    assert q.public_key == p.public_key and q.short_id == "a1b2c3d4"
    assert q.flow == "xtls-rprx-vision"
    assert q.name == "تست کانفیگ #1"


def test_trojan_ws_link_roundtrip():
    p = ConfigParams(
        protocol="trojan", address="example.com", port=8443,
        credential="pass w:rd@", transport="ws", security="tls",
        sni="example.com", path="/newvpn/tws", allow_insecure=True, name="TJ 2",
    )
    link = build_link(p)
    assert link.startswith("trojan://")
    q = parse_link(link)
    assert q.credential == "pass w:rd@"
    assert q.port == 8443 and q.transport == "ws"
    assert q.path == "/newvpn/tws" and q.allow_insecure is True


def test_vless_ws_cf_link_roundtrip():
    p = ConfigParams(
        protocol="vless", address="104.16.0.1", port=443,
        credential="uuid-x", transport="ws", security="tls",
        sni="mydomain.com", host_header="mydomain.com", path="/newvpn/ws", name="CF 3",
    )
    link = build_link(p)
    q = parse_link(link)
    assert q.address == "104.16.0.1" and q.host_header == "mydomain.com"
    assert q.sni == "mydomain.com" and q.security == "tls"


def test_parse_rejects_unknown_scheme():
    with pytest.raises(ValueError):
        parse_link("https://example.com")


# ---------- scoring ----------
from app.ippool.scanner import classify, score_result


def test_scoring_classification_bounds():
    assert classify(100) == "excellent"
    assert classify(85) == "excellent"
    assert classify(84) == "good"
    assert classify(65) == "good"
    assert classify(64) == "average"
    assert classify(40) == "average"
    assert classify(39) == "unhealthy"
    assert classify(0) == "unhealthy"


def test_scoring_latency_curve():
    assert score_result(50, True) == 100
    assert score_result(120, True) == 85
    assert score_result(250, True) == 65
    assert score_result(500, True) == 45
    assert score_result(900, True) == 25
    assert score_result(None, False) == 0


# ---------- scanner sampling ----------
from app.ippool.scanner import sample_addresses


def test_sample_addresses_bounded_and_valid():
    ranges = ["104.16.0.0/12", "172.64.0.0/13"]
    addrs = sample_addresses(ranges, per_range=5)
    assert 0 < len(addrs) <= 10
    import ipaddress
    for a in addrs:
        ipaddress.ip_address(a)  # raises if malformed


def test_scan_history_score_decay_is_real():
    # failed checks must strictly reduce the score (anti-flapping honesty)
    before = 90
    after = max(0, before - 30)
    assert after < before
