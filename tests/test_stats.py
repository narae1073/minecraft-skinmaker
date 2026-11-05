"""Daily conversion counters: aggregate attempts/success, KST, private file."""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend import stats

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 5, 12, 0, tzinfo=KST)


def test_record_attempt_and_success():
    stats.record_attempt(now=NOW)
    stats.record_success("classic", 3, 12.5, now=NOW)

    data = json.loads(stats.STATS_PATH.read_text(encoding="utf-8"))
    row = data["days"]["2026-11-05"]
    assert row["attempts"] == 1
    assert row["success"] == 1
    assert row["classic"] == 1
    assert row["candidates"] == 3
    assert row["total_seconds"] == 12.5
    assert stats.STATS_PATH.stat().st_mode & 0o777 == 0o600


def test_kst_day_boundary():
    # 2026-11-04 23:30 UTC == 2026-11-05 08:30 KST.
    stats.record_attempt(now=datetime(2026, 11, 4, 23, 30, tzinfo=timezone.utc))
    assert "2026-11-05" in stats.load()["days"]
    assert "2026-11-04" not in stats.load()["days"]


def test_recent_includes_empty_days():
    rows = stats.recent(days=3, now=NOW)
    assert [day for day, _ in rows] == ["2026-11-03", "2026-11-04", "2026-11-05"]
    assert rows[-1][1] == {}


def test_daily_stats_script_prints_attempts_success_and_failures(tmp_path):
    path = tmp_path / "daily.json"
    today = stats.today()
    path.write_text(json.dumps({
        "version": 1,
        "days": {today: {"attempts": 3, "success": 2, "classic": 2, "slim": 0,
                         "candidates": 2, "total_seconds": 6.0}},
    }), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "daily_stats.py"),
         "--path", str(path), "--days", "2"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert today in result.stdout
    assert "3" in result.stdout and "2" in result.stdout
    assert "attempts" in result.stdout and "success" in result.stdout and "failed" in result.stdout
