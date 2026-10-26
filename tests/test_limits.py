"""Public-demo guards: rate limiter + upload cap helpers (no app import)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlette.requests import Request

from backend.limits import RateLimiter, client_ip, max_upload_bytes


def test_allows_up_to_the_limit_then_blocks():
    rl = RateLimiter(limit=2, window=60)
    assert rl.allow("a", now=0.0)
    assert rl.allow("a", now=1.0)
    assert not rl.allow("a", now=2.0)
    # different key is independent
    assert rl.allow("b", now=2.0)


def test_window_slides():
    rl = RateLimiter(limit=1, window=10)
    assert rl.allow("a", now=0.0)
    assert not rl.allow("a", now=9.9)
    assert rl.allow("a", now=10.0)


def test_zero_limit_disables():
    rl = RateLimiter(limit=0)
    assert all(rl.allow("a", now=float(i)) for i in range(100))


def test_env_limit_and_upload_cap(monkeypatch):
    monkeypatch.setenv("SKINMAKER_RATE_LIMIT_PER_MIN", "3")
    monkeypatch.setenv("SKINMAKER_MAX_UPLOAD_MB", "2")
    assert RateLimiter().limit == 3
    assert max_upload_bytes() == 2 * 1024 * 1024
    monkeypatch.setenv("SKINMAKER_MAX_UPLOAD_MB", "garbage")
    assert max_upload_bytes() == 15 * 1024 * 1024


def _request(peer, headers=None):
    scope = {
        "type": "http",
        "client": (peer, 12345),
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
    }
    return Request(scope)


def test_client_ip_trusts_cloudflare_header_only_from_loopback():
    assert client_ip(_request("127.0.0.1", {"CF-Connecting-IP": "1.2.3.4"})) == "1.2.3.4"
    assert client_ip(_request("10.0.0.5", {"CF-Connecting-IP": "1.2.3.4"})) == "10.0.0.5"


def test_client_ip_falls_back_to_x_forwarded_for_then_peer():
    assert client_ip(_request("127.0.0.1", {"X-Forwarded-For": "5.6.7.8, 10.0.0.1"})) == "5.6.7.8"
    assert client_ip(_request("10.0.0.5", {"X-Forwarded-For": "5.6.7.8"})) == "10.0.0.5"
