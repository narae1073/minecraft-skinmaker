"""held-out 라벨링 풀 샘플러 + 라벨 검증기. 모델 코드를 건드리지 않는 측정 인프라.

    python -m skinmaker.heldout                          # 현 풀에서 후보 요약 + 부족분
    python -m skinmaker.heldout --n 45 --out docs/superpowers/specs/heldout_manifest.json
    python -m skinmaker.heldout --source <새 사진 폴더>   # 풀 부족분 보충용
    python -m skinmaker.heldout --validate heldout_labels.json          # 라벨 파일 검증
    python -m skinmaker.heldout --validate heldout_labels.json \
        --heldout-source <새 폴더>       # 키 + 내용 해시까지 무겹 검증

배경 (docs/superpowers/specs/2026-10-11-heldout-protocol.md):
- bottom_labels.json 의 59장은 F1 상수 과적합과 F2·grain 기각에 쓰였으므로
  이제 "적합(fitting) 세트"다. 평가용 held-out 은 그 키 전부와 무겹게 만든다.
- 프레이밍 밴드 컷은 eval.report_band 상수를 직접 import한다 (이중 정의 금지).
"""
from __future__ import annotations

import argparse
import hashlib
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
# 해시 캐시. out/ 는 .gitignore 라 이미 무시된다 (gitignore:4).
CACHE_PATH = Path(__file__).resolve().parent.parent / "out" / "heldout_hash_cache.json"
KNOWN_CATEGORIES_FALLBACK = ("blue", "dark", "light", "mid", "colored", "none", "unclear")


def sha256_file(path: Path, cache_path: Path | None = None) -> str:
    """파일 바이트의 SHA-256. cache_path 주면 size+mtime이 같으면 재계산 없이 캐시값."""
    st = path.stat()
    if cache_path is not None and cache_path.exists():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            data = {}
        entry = data.get(str(path.resolve()))
        if entry and entry.get("size") == st.st_size and entry.get("mtime_ns") == st.st_mtime_ns:
            return str(entry["sha256"])
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if cache_path is not None:
        data = {}
        if cache_path.exists():
            try:
                data = json.loads(cache_path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                data = {}
        data[str(path.resolve())] = {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "sha256": digest}
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(data), encoding="utf-8")
    return digest


def labeled_photo_hashes(source: Path, label_keys, cache_path: Path | None = None) -> dict[str, str]:
    """라벨 키 -> 소스 폴더에서 해석한 파일의 SHA-256. 없는 키는 무시한다."""
    out: dict[str, str] = {}
    for key in label_keys:
        p = source / key
        if p.exists() and p.is_file():
            out[key] = sha256_file(p, cache_path)
    return out


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
    candidates: list[tuple],
    labels: dict[str, str],
    labeled_hashes: set[str] | None = None,
) -> tuple[list[dict], list[dict]]:
    """라벨·얼굴 검출·내용 해시로 스크리닝. inspect 결과 PhotoInput 을 받는다 (검출 주입 가능).

    candidates 항목: (name, PhotoInput) 또는 (name, PhotoInput, file_sha256).
    제외 순서: already_labeled (파일명, 보수적) -> duplicate_content (내용 해시) -> no_face.
    """
    kept: list[dict] = []
    excluded: list[dict] = []
    for item in candidates:
        name, photo = item[0], item[1]
        file_hash = item[2] if len(item) > 2 else None
        ratio = photo.face.h / photo.image.size[1] if photo.face is not None else None
        if name in labels:
            excluded.append({"photo": name, "reason": "already_labeled"})
        elif labeled_hashes is not None and file_hash is not None and file_hash in labeled_hashes:
            excluded.append({"photo": name, "reason": "duplicate_content"})
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


def build_candidates(
    source: Path,
    suffixes: tuple[str, ...] | None = None,
    cache_path: Path | None = CACHE_PATH,
) -> list[tuple]:
    """폴더를 훑어 inspect + 내용 해시. 판독 실패 파일은 SKIP 하고 건너뛴다."""
    if suffixes is None:
        from .measure import SUFFIXES

        suffixes = SUFFIXES
    out: list[tuple] = []
    for p in sorted(source.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in suffixes:
            continue
        try:
            photo = inspect(p)
        except Exception as exc:
            print(f"SKIP {p.name}: {type(exc).__name__} {exc}")
            continue
        out.append((p.name, photo, sha256_file(p, cache_path)))
    return out


def validate_heldout_labels(
    heldout_path: Path,
    bottom_path: Path,
    bottom_source: Path | None = None,
    heldout_source: Path | None = None,
    cache_path: Path | None = None,
) -> list[str]:
    """heldout_labels.json 검증: (a) bottom_labels.json 무겹 (키 + 내용 해시), (b) 스키마 호환.

    성공이면 [] 를, 문제는 사람이 읽는 메시지(str) 목록으로 돌려준다.
    """
    bottom_raw = json.loads(Path(bottom_path).read_text(encoding="utf-8"))
    try:
        heldout_raw = json.loads(Path(heldout_path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [f"shape: held-out 라벨 파일 없음: {heldout_path}"]
    if not isinstance(heldout_raw, dict) or not isinstance(heldout_raw.get("labels"), dict):
        return ["shape: 상위 'labels' 객체가 없다 — bottom_labels.json 과 같은 스키마 필요"]
    held = heldout_raw["labels"]
    if not isinstance(bottom_path, Path) or not Path(bottom_path).exists():
        return [f"shape: bottom 라벨 파일 없음: {bottom_path}"]
    bottom = bottom_raw.get("labels", {}) if isinstance(bottom_raw, dict) else {}
    categories = set(bottom_raw.get("categories") or KNOWN_CATEGORIES_FALLBACK)

    problems: list[str] = []
    for key, val in held.items():
        if val not in categories:
            problems.append(f"unknown_category: {key}={val!r} (알려진 범주: {sorted(categories)})")
    for key in sorted(set(held) & set(bottom)):
        problems.append(f"overlap_key: {key} 은 bottom_labels.json 에 이미 라벨되어 있다")
    if bottom_source is not None and heldout_source is not None:
        bh = labeled_photo_hashes(Path(bottom_source), bottom, cache_path)
        hh = labeled_photo_hashes(Path(heldout_source), held, cache_path)
        by_hash: dict[str, list[str]] = {}
        for key, digest in bh.items():
            by_hash.setdefault(digest, []).append(key)
        for key, digest in hh.items():
            if digest in by_hash:
                problems.append(f"overlap_content: {key} 은 {','.join(by_hash[digest])} 와(과) 같은 내용이다")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="skinmaker.heldout")
    ap.add_argument("--source", default=str(DEFAULT_SOURCE))
    ap.add_argument("--labels", default=str(DEFAULT_LABELS))
    ap.add_argument("--n", type=int, default=45)
    ap.add_argument("--out", default=None, help="manifest 저장 경로 (기본: 쓰지 않음)")
    ap.add_argument(
        "--validate",
        default=None,
        metavar="HELDOUT_LABELS",
        help="라벨 파일 검증 모드: 무겹(키·해시) + 스키마. 위반이 있으면 exit 1",
    )
    ap.add_argument("--heldout-source", default=None, help="검증 모드에서 held-out 사진 폴더 (내용 해시 대조용)")
    ap.add_argument("--scene-note", default=None, help="조명·장면 특이점 기록 (manifest lighting_scene_note)")
    args = ap.parse_args(argv)

    if args.validate:
        problems = validate_heldout_labels(
            Path(args.validate),
            Path(args.labels),
            bottom_source=Path(args.source),
            heldout_source=Path(args.heldout_source) if args.heldout_source else None,
            cache_path=CACHE_PATH,
        )
        if problems:
            print(f"held-out 라벨 검증 실패 ({len(problems)}건):")
            for problem in problems:
                print(f"  - {problem}")
            print("라벨 파일을 고친 뒤 같은 명령을 다시 실행하라. 동결(커밋)은 검증 통과 후에.")
            return 1
        print(f"held-out 라벨 검증 통과: {args.validate}")
        print("bottom_labels.json과 키·내용 무겹, 스키마 호환. bottom_eval --labels 로 게이트를 측정할 수 있다.")
        return 0

    labels = json.loads(Path(args.labels).read_text(encoding="utf-8"))["labels"]
    candidates = build_candidates(Path(args.source))
    known_hashes = set(labeled_photo_hashes(Path(args.source), labels, CACHE_PATH).values())
    kept, excluded = collect(candidates, labels, labeled_hashes=known_hashes)

    counts = {b: sum(1 for k in kept if k["band"] == b) for b in BAND_ORDER}
    budget = band_budget(counts, args.n)
    picked = select(kept, min(args.n, len(kept)))
    shortfall = max(0, args.n - len(kept))

    print(f"source: {args.source}")
    print(f"excluded: {len(excluded)} (already_labeled {sum(1 for e in excluded if e['reason'] == 'already_labeled')} / duplicate_content {sum(1 for e in excluded if e['reason'] == 'duplicate_content')} / no_face {sum(1 for e in excluded if e['reason'] == 'no_face')})")
    print(f"available (disjoint, face detected): {len(kept)}  by band {counts}")
    print(f"budget for n={args.n}: {budget}")
    print(f"selected now: {len(picked)}  -> shortfall vs target: {shortfall}")
    if shortfall > 0:
        print(
            f"WARNING: 목표 {args.n}장에 {len(kept)}장 가능 — 부족 {shortfall}. "
            "held-out 통계(게이트 판정표)가 n에 따라 달라진다: protocol §4 표를 n에 맞춰 쓰고, 나머지는 새 사진으로 채울 것."
        )
    else:
        print("shortfall 원인: 풀 98장 중 83장이 이미 bottom_labeler 에 라벨되어 있다.")
        print("보충은 새 사진 폴더를 --source 로 넣어 같은 명령을 다시 실행한다.")

    exit_code = 1 if shortfall > 0 else 0
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
            "lighting_scene_note": args.scene_note,
        }
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"saved {args.out}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
