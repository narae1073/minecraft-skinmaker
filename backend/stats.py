"""Daily conversion counters in KST.

Aggregate counts only: no IP addresses, cookies, photos, or user identifiers.
The file lives under ``backend/private/stats`` (never served) and is not part of
the 14-day media cleanup, so daily totals survive.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATS_DIR = ROOT / "private" / "stats"
STATS_PATH = STATS_DIR / "daily.json"
KST = timezone(timedelta(hours=9))
_LOCK = threading.Lock()


def _kst(now: datetime | None = None) -> datetime:
    value = now or datetime.now(KST)
    if value.tzinfo is None:
        value = value.replace(tzinfo=KST)
    return value.astimezone(KST)


def today(now: datetime | None = None) -> str:
    return _kst(now).date().isoformat()


def load() -> dict:
    try:
        data = json.loads(STATS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    days = data.get("days")
    return {"version": 1, "days": days if isinstance(days, dict) else {}}


def _save(data: dict) -> None:
    STATS_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=STATS_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, sort_keys=True)
        os.chmod(tmp, 0o600)
        os.replace(tmp, STATS_PATH)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _bump(now: datetime | None = None, **fields) -> None:
    with _LOCK:
        data = load()
        row = data["days"].setdefault(today(now), {})
        for key, value in fields.items():
            row[key] = row.get(key, 0) + value
        try:
            _save(data)
        except OSError:
            # Statistics are best-effort; never fail a conversion for them.
            pass


def record_attempt(now: datetime | None = None) -> None:
    _bump(now, attempts=1)


def record_success(model: str, candidates: int, total_seconds: float,
                   now: datetime | None = None) -> None:
    _bump(now, success=1, candidates=int(candidates),
          total_seconds=round(float(total_seconds), 3), **{model: 1})


def recent(days: int = 30, now: datetime | None = None) -> list[tuple[str, dict]]:
    data = load()
    end = _kst(now).date()
    out: list[tuple[str, dict]] = []
    for offset in range(max(1, days) - 1, -1, -1):
        day = (end - timedelta(days=offset)).isoformat()
        out.append((day, data["days"].get(day, {})))
    return out
