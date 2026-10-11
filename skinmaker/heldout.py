"""held-out 라벨링 풀 샘플러. 모델 코드를 건드리지 않는 측정 인프라.

    python -m skinmaker.heldout                          # 현 풀에서 후보 요약 + 부족분
    python -m skinmaker.heldout --n 45 --out docs/superpowers/specs/heldout_manifest.json
    python -m skinmaker.heldout --source <새 사진 폴더>   # 풀 부족분 보충용

배경 (docs/superpowers/specs/2026-10-11-heldout-protocol.md):
- bottom_labels.json 의 59장은 F1 상수 과적합과 F2·grain 기각에 쓰였으므로
  이제 "적합(fitting) 세트"다. 평가용 held-out 은 그 키 전부와 무겹게 만든다.
- 프레이밍 밴드 컷은 eval.report_band 상수를 직접 import한다 (이중 정의 금지).
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from PIL import Image

from .eval import REPORT_FULL_MAX, REPORT_MID_MAX
from .quality import PhotoInput, inspect

DEFAULT_SOURCE = Path(__file__).resolve().parent.parent / "out" / "s0_photos"
DEFAULT_LABELS = Path(__file__).resolve().parent.parent / "docs" / "superpowers" / "specs" / "bottom_labels.json"
MANIFEST_PATH = Path(__file__).resolve().parent.parent / "docs" / "superpowers" / "specs" / "heldout_manifest.json"
BAND_ORDER = ("full", "mid", "portrait")


def framing_band(ratio: float) -> str:
    """고정 세트와 같은 컷 (eval.report_band, full<0.10 / mid<0.20 / portrait>=0.20)."""
    if ratio < REPORT_FULL_MAX:
        return "full"
    if ratio < REPORT_MID_MAX:
        return "mid"
    return "portrait"


def evenly_spaced(items: list, n: int) -> list:
    """ratio 정렬 목록에서 n개를 균등 간격 인덱스로 뽑는다 (결정적, 무작위 없음).

    fixed10 선정과 같은 방식 ("evenly spaced by ratio within band").
    """
    if n <= 0 or not items:
        return []
    if n >= len(items):
        return list(items)
    if n == 1:
        return [items[0]]
    step = (len(items) - 1) / (n - 1)
    idx = [round(i * step) for i in range(n)]
    return [items[i] for i in idx]


def band_budget(bands: dict[str, int], n: int) -> dict[str, int]:
    """밴드별 목표수 = 비례 배분 + 최대나머지. 풀 크기의 상한을 넘지 않는다."""
    total = sum(bands.values())
    out: dict[str, int] = dict.fromkeys(bands, 0)
    if total == 0 or n <= 0:
        return out
    quotas = {b: v / total * n for b, v in bands.items()}
    base = {b: min(int(q), bands[b]) for b, q in quotas.items()}
    rest = n - sum(base.values())
    order = sorted(bands, key=lambda b: (quotas[b] - base[b], -BAND_ORDER.index(b)), reverse=True)
    for b in order:
        if rest <= 0:
            break
        add = min(1, rest, bands[b] - base[b])
        if add > 0:
            base[b] += add
            rest -= add
    return base


def collect(
    candidates: list[tuple[str, PhotoInput]],
    labels: dict[str, str],
) -> tuple[list[dict], list[dict]]:
    """라벨·얼굴 검출로 스크리닝. inspect 결과 PhotoInput 을 받는다 (검출 주입 가능)."""
    kept: list[dict] = []
    excluded: list[dict] = []
    for name, photo in candidates:
        ratio = photo.face.h / photo.image.size[1] if photo.face is not None else None
        if name in labels:
            excluded.append({"photo": name, "reason": "already_labeled"})
        elif photo.rejected or ratio is None:
            excluded.append({"photo": name, "reason": "no_face"})
        else:
            kept.append(
                {
                    "photo": name,
                    "band": framing_band(ratio),
                    "face_h_over_img_h": round(ratio, 4),
                    "face_box": [photo.face.x, photo.face.y, photo.face.w, photo.face.h],
                }
            )
    kept.sort(key=lambda k: k["face_h_over_img_h"])
    return kept, excluded


def select(kept: list[dict], n: int) -> list[dict]:
    """밴드별 예산 배분 후 각 밴드에서 균등 인덱스 선택 (결정적)."""
    bands: dict[str, list[dict]] = {b: [] for b in BAND_ORDER}
    for k in kept:
        bands[k["band"]].append(k)
    budget = band_budget({b: len(v) for b, v in bands.items()}, n)
    out: list[dict] = []
    for b in BAND_ORDER:
        picked = evenly_spaced(bands[b], budget.get(b, 0))
        out.extend(picked)
    return out


def build_candidates(source: Path, suffixes: tuple[str, ...] | None = None) -> list[tuple[str, PhotoInput]]:
    """폴더를 훑어 inspect 한다. 검출 실패는 collect 에서 제외된다."""
    if suffixes is None:
        from .measure import SUFFIXES

        suffixes = SUFFIXES
    out: list[tuple[str, PhotoInput]] = []
    for p in sorted(source.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in suffixes:
            continue
        out.append((p.name, inspect(p)))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="skinmaker.heldout")
    ap.add_argument("--source", default=str(DEFAULT_SOURCE))
    ap.add_argument("--labels", default=str(DEFAULT_LABELS))
    ap.add_argument("--n", type=int, default=45)
    ap.add_argument("--out", default=None, help="manifest 저장 경로 (기본: 쓰지 않음)")
    args = ap.parse_args(argv)

    labels = json.loads(Path(args.labels).read_text(encoding="utf-8"))["labels"]
    candidates = build_candidates(Path(args.source))
    kept, excluded = collect(candidates, labels)

    counts = {b: sum(1 for k in kept if k["band"] == b) for b in BAND_ORDER}
    budget = band_budget(counts, args.n)
    picked = select(kept, min(args.n, len(kept)))
    shortfall = max(0, args.n - len(kept))

    print(f"source: {args.source}")
    print(f"excluded: {len(excluded)} (already_labeled {sum(1 for e in excluded if e['reason'] == 'already_labeled')} / no_face {sum(1 for e in excluded if e['reason'] == 'no_face')})")
    print(f"available (disjoint, face detected): {len(kept)}  by band {counts}")
    print(f"budget for n={args.n}: {budget}")
    print(f"selected now: {len(picked)}  -> shortfall vs target: {shortfall}")
    print("shortfall 원인: 풀 98장 중 83장이 이미 bottom_labeler 에 라벨되어 있다.")
    print("보충은 새 사진 폴더를 --source 로 넣어 같은 명령을 다시 실행한다.")

    if args.out:
        payload = {
            "generated": date.today().isoformat(),
            "source": str(args.source),
            "labels_used": str(args.labels),
            "target_n": args.n,
            "counts": counts,
            "budget": budget,
            "selected": picked,
            "excluded": excluded,
            "shortfall": shortfall,
        }
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"saved {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
