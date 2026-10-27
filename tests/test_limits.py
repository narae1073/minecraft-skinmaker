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
    assert rl.tracked_keys == 0


def test_idle_keys_are_evicted_after_the_window():
    """키가 무한정 쌓이지 않는다 — 창이 지난 키는 다음 sweep 에서 사라진다."""
    rl = RateLimiter(limit=10, window=60)
    for i in range(50):
        assert rl.allow(f"ip-{i}", now=0.0)
    assert rl.tracked_keys == 50
    assert rl.allow("new", now=61.0)
    assert rl.tracked_keys == 1


def test_sweep_does_not_reset_active_counts():
    """sweep 은 만료된 hit 만 지운다 — 최근 hit 의 한도 계산은 유지된다."""
    rl = RateLimiter(limit=2, window=60)
    assert rl.allow("a", now=0.0)
    assert rl.allow("a", now=1.0)
    # t=60 sweep 은 t=0 hit 만 만료시킨다. t=1 hit + 새 hit 까지 2회가 한도.
    assert rl.allow("a", now=60.0)
    assert not rl.allow("a", now=60.1)


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
