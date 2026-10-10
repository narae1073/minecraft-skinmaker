"""하의 색 평가 하네스: 사람이 붙인 범주 라벨과 S1 측정값을 비교한다.

    python -m skinmaker.bottom_eval                 # 마스크 on / off A/B
    python -m skinmaker.bottom_eval --json out/bottom_eval.json

라벨: docs/superpowers/specs/bottom_labels.json (시각 판정, 범주 단위).
범주: blue(데님 등 청색) · dark · light · mid(회색·카키) · colored · none(하의 안 보임) · unclear.
라벨이 none/unclear 인 사진은 정확도 분모에서 뺀다 (none 은 "기권"이 맞는지만 따로 센다).
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np

from . import colors as C
from .measure import SUFFIXES
from .quality import inspect

LABELS_PATH = Path(__file__).resolve().parent.parent / "docs" / "superpowers" / "specs" / "bottom_labels.json"
SOURCE_DIR = Path(__file__).resolve().parent.parent / "out" / "s0_photos"
CATEGORIES = ("blue", "dark", "light", "mid", "colored")
BLUE_CHROMA_MIN = 0.05  # B-R 크로마 차. 짙은 데님(#374047)은 0.057, 검정 바지는 0.
COLORED_SAT_MIN = 0.25  # (max-min)/max
COLORED_VALUE_MIN = 0.25  # max(r,g,b). 이보다 어두우면 색조가 있어도 어두운 옷으로 본다


def categorize(sample: C.ColorSample) -> str:
    """측정 색 하나를 범주로. 결측이면 'missing'."""
    if sample.missing:
        return "missing"
    r, g, b = (c / 255.0 for c in sample.rgb)
    total = r + g + b
    if total > 0 and (b / total - r / total) >= BLUE_CHROMA_MIN and C.luma(np.asarray(sample.rgb, np.float32)) >= 40:
        return "blue"
    mx, mn = max(r, g, b), min(r, g, b)
    # 명도가 낮으면 채도 비율은 의미가 없다 (#010b18 의 (mx-mn)/mx 는 0.96 이지만 검정이다).
    if mx >= COLORED_VALUE_MIN and (mx - mn) / mx > COLORED_SAT_MIN:
        return "colored"
    lum = C.luma(np.asarray(sample.rgb, np.float32))
    if lum < 85:
        return "dark"
    if lum >= 175:
        return "light"
    return "mid"


def load_labels(path: Path = LABELS_PATH) -> dict[str, str]:
    return json.loads(Path(path).read_text(encoding="utf-8"))["labels"]


def evaluate(labels: dict[str, str], source_dir: Path = SOURCE_DIR, wb_clipped: bool = False) -> list[dict]:
    rows = []
    for rel, label in labels.items():
        path = source_dir / rel
        if not path.exists():
            continue
        try:
            photo = inspect(path)
        except Exception:
            continue
        if photo.rejected:
            rows.append({"photo": rel, "label": label, "rejected": True})
            continue
        C.LOWER_BODY_MASK_ENABLED = True
        C.WB_APPLY_CLIPPED = wb_clipped
        try:
            on = C.extract(photo)
        finally:
            C.WB_APPLY_CLIPPED = False
        C.LOWER_BODY_MASK_ENABLED = False
        try:
            off = C.extract(photo)
        finally:
            C.LOWER_BODY_MASK_ENABLED = True
        rows.append(
            {
                "photo": rel,
                "label": label,
                "rejected": False,
                "on_hex": on.bottom.hex,
                "on_cat": categorize(on.bottom),
                "on_conf": on.bottom.confident,
                "on_plausible": on.bottom_plausible,
                "on_rgb": list(on.bottom.rgb),
                "off_hex": off.bottom.hex,
                "off_cat": categorize(off.bottom),
                "off_conf": off.bottom.confident,
                "mask_changed": on.bottom.hex != off.bottom.hex,
            }
        )
    return rows


def summarize(rows: list[dict], variant: str) -> dict:
    """variant: 'on' 또는 'off'. 라벨이 범주인 사진(legs 보임)만 정확도 분모."""
    scored = [r for r in rows if not r.get("rejected") and r["label"] in CATEGORIES]
    agree = sum(1 for r in scored if r[f"{variant}_cat"] == r["label"])
    abstain = sum(1 for r in scored if r[f"{variant}_cat"] == "missing")
    confusion: Counter = Counter()
    for r in scored:
        confusion[(r["label"], r[f"{variant}_cat"])] += 1
    none_rows = [r for r in rows if not r.get("rejected") and r["label"] == "none"]
    none_hallucinated = sum(1 for r in none_rows if r[f"{variant}_cat"] != "missing")
    return {
        "variant": variant,
        "scored": len(scored),
        "agree": agree,
        "agreement": round(agree / len(scored), 3) if scored else None,
        "abstain": abstain,
        "wrong_nonabstain": len(scored) - agree - abstain,
        "none_labeled": len(none_rows),
        "none_with_bottom_measured": none_hallucinated,
        "unclear_excluded": sum(1 for r in rows if r["label"] == "unclear"),
        "confusion": {f"{l}->{m}": n for (l, m), n in sorted(confusion.items())},
    }


DEFAULT_BOTTOM_RGB = (60, 68, 80)  # render.DEFAULT_BOTTOM (#3c4450)


def policy_summary(rows: list[dict], name: str) -> dict:
    """렌더 폴백 정책별 정확도. 렌더가 실제로 그리는 하의 색을 범주로 비교한다."""
    from .render import bottom_usable

    scored = [r for r in rows if not r.get("rejected") and r["label"] in CATEGORIES]
    agree = 0
    used_measured = 0
    for r in scored:
        sample = C.ColorSample(r["on_hex"], 0.0, r["on_conf"], tuple(r["on_rgb"]), 1)
        if name == "default_only":
            usable = False
        elif name == "confident_only":
            usable = not sample.missing and sample.confident
        elif name == "trust_measured":
            usable = not sample.missing
        elif name == "gate":
            usable = bottom_usable(sample, r["on_plausible"])
        else:
            raise ValueError(name)
        used_measured += int(usable)
        rgb = tuple(r["on_rgb"]) if usable else DEFAULT_BOTTOM_RGB
        rendered = C.ColorSample("#%02x%02x%02x" % rgb, 1.0, True, rgb, 1)
        if categorize(rendered) == r["label"]:
            agree += 1
    return {
        "policy": name,
        "scored": len(scored),
        "agree": agree,
        "agreement": round(agree / len(scored), 3) if scored else None,
        "measured_used": used_measured,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="skinmaker.bottom_eval")
    ap.add_argument("--labels", default=str(LABELS_PATH))
    ap.add_argument("--source", default=str(SOURCE_DIR))
    ap.add_argument("--json", default=None, help="행 단위 결과 저장 경로")
    ap.add_argument("--wb-clipped", action="store_true", help="클립된 WB 게인도 적용하는 변형")
    args = ap.parse_args(argv)
    rows = evaluate(load_labels(Path(args.labels)), Path(args.source), wb_clipped=args.wb_clipped)
    summaries = [summarize(rows, v) for v in ("on", "off")]
    for s in summaries:
        print(f"[mask {s['variant']:3s}] scored={s['scored']} agree={s['agree']} "
              f"agreement={s['agreement']} abstain={s['abstain']} wrong={s['wrong_nonabstain']} "
              f"none_labeled={s['none_labeled']} none_with_bottom={s['none_with_bottom_measured']}")
    policies = [policy_summary(rows, n) for n in ("default_only", "confident_only", "trust_measured", "gate")]
    print("render fallback policy (bottom, labeled legs-visible photos):")
    for pol in policies:
        print(f"  {pol['policy']:16s} agreement={pol['agreement']} ({pol['agree']}/{pol['scored']}) measured_used={pol['measured_used']}")
    changed = [r for r in rows if r.get("mask_changed")]
    print(f"mask changed bottom on {len(changed)} / {sum(1 for r in rows if not r.get('rejected'))} photos")
    print("confusion (mask on, label->measured):")
    for k, v in summaries[0]["confusion"].items():
        print(f"  {k:18s} {v}")
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps({"summary": summaries, "policies": policies, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"saved {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
