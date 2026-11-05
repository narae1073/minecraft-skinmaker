#!/usr/bin/env python3
"""Print daily conversion counts (KST) from backend/private/stats/daily.json."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import stats  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Daily conversion counts (KST)")
    parser.add_argument("--days", type=int, default=30, help="number of days to print")
    parser.add_argument("--path", type=Path, default=None, help="override daily.json path")
    args = parser.parse_args(argv)
    if args.path is not None:
        stats.STATS_PATH = args.path
        stats.STATS_DIR = args.path.parent

    rows = stats.recent(days=max(1, args.days))
    header = f"{'date':<12}{'attempts':>9}{'success':>9}{'failed':>8}{'classic':>8}{'slim':>6}{'candidates':>11}{'avg_s':>8}"
    print(header)
    total_attempts = total_success = 0
    for day, row in rows:
        attempts = int(row.get("attempts", 0))
        success = int(row.get("success", 0))
        classic = int(row.get("classic", 0))
        slim = int(row.get("slim", 0))
        candidates = int(row.get("candidates", 0))
        total_seconds = float(row.get("total_seconds", 0.0))
        avg = total_seconds / success if success else 0.0
        total_attempts += attempts
        total_success += success
        print(f"{day:<12}{attempts:>9}{success:>9}{max(0, attempts - success):>8}"
              f"{classic:>8}{slim:>6}{candidates:>11}{avg:>8.1f}")
    print(f"{'total':<12}{total_attempts:>9}{total_success:>9}"
          f"{max(0, total_attempts - total_success):>8}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
