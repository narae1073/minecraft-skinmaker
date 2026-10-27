"""Batch photo → skin pipeline + QA render harness (2026-10-28).

Runs the same pipeline as `POST /api/v1/generate-skin` over a photo directory,
saves per-photo JSON/skins, optionally renders the 3D QA pair, and writes a
manifest + a QA selection file. Resumable: completed photos are skipped.

    # curated run (explicit list of paths relative to --photos)
    python -m skinmaker.batch --photos out/people_photos_original \
        --photo-list out/qa_batch/curated_photos.txt --out out/qa_batch \
        --transport gemini --sleep 3 --render --render-out out/qa_render_batch

    # full validation (single VLM query, no renders)
    python -m skinmaker.batch --photos out/people_photos_original --out out/qa_batch_full \
        --transport gemini --single --sleep 3

Per photo: `<out>/<relative>/result.json`, `skin_c1.png` (+ candidates).
With `--render`: `<render-out>/<relative>/{front_right,back_right,contact_sheet,compare}.png`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import parsing
from .attributes import summarize
from .candidates import build
from .classify import classify, framing
from .colors import extract
from .measure import SUFFIXES
from .quality import inspect
from .render import resolve_bottom_ex
from .vlm import get_transport
from .vlm.mock import MockTransport

DEFAULT_OUT = "out/qa_batch"
DEFAULT_RENDER_OUT = "out/qa_render_batch"
DEFAULT_MODEL = "classic"


class ReplayTransport(MockTransport):
    """저장된 VLM JSON을 재생한다 — 코드/렌더 수정 후 API 호출 없이 재처리."""
    name = "replay"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def supported(path: Path) -> bool:
    return path.suffix.lower() in SUFFIXES


def discover(root: Path, photo_list: Path | None = None) -> list[Path]:
    """Photos under root (recursive), or an explicit relative-path list."""
    root = Path(root)
    if photo_list is None:
        # 확장자 없는 파일(예: images24jpeg)도 포함 — PIL 이 내용으로 판별하고,
        # 열 수 없으면 해당 사진만 error 로 기록된다.
        return sorted(
            p for p in root.rglob("*")
            if p.is_file() and (supported(p) or not p.suffix)
        )
    lines = Path(photo_list).read_text(encoding="utf-8").splitlines()
    picked: list[Path] = []
    missing: list[str] = []
    for line in lines:
        rel = line.strip()
        if not rel or rel.startswith("#"):
            continue
        p = root / rel
        (picked if p.is_file() else missing).append(p if p.is_file() else rel)
    if missing:
        raise FileNotFoundError(f"photo list entries missing under {root}: {missing[:5]}")
    return picked


def relative_key(root: Path, path: Path) -> str:
    """POSIX relative path; used as the output directory and manifest key."""
    try:
        return path.resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return path.name


def _inspect_input(path: Path, max_side: int, tmp_dir: Path):
    """inspect() on a size-capped copy (large photos cost seconds in SCHP/colour)."""
    with Image.open(path) as probe:
        probe = probe.convert("RGB")
        width, height = probe.size
        if max_side and max(width, height) > max_side:
            scale = max_side / max(width, height)
            resized = probe.resize((max(1, int(width * scale)), max(1, int(height * scale))), Image.LANCZOS)
            tmp = tmp_dir / f"{hashlib.sha256(str(path).encode()).hexdigest()[:16]}.png"
            resized.save(tmp)
            photo = inspect(tmp)
            return photo, tmp
    return inspect(path), None


def _classify_with_retry(photo, transport, single: bool, attempts: int = 3):
    result = None
    for attempt in range(attempts):
        result = classify(photo, transport, double_check=not single)
        if result.ok:
            return result
        if result.error_kind == "transport":
            break
        time.sleep(1.5 * (attempt + 1))
    return result


def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def process_photo(
    path: Path,
    root: Path,
    *,
    out_dir: Path,
    transport,
    single: bool = False,
    skin_model: str = DEFAULT_MODEL,
    max_side: int = 2048,
    render: bool = False,
    render_out: Path | None = None,
) -> dict:
    rel = relative_key(root, path)
    dest = out_dir / rel
    dest.mkdir(parents=True, exist_ok=True)
    result_path = dest / "result.json"
    raw = path.read_bytes()
    record: dict = {
        "source": rel,
        "status": "ok",
        "error": None,
        "image": {
            "size": list(Image.open(path).size),
            "sha256": hashlib.sha256(raw).hexdigest(),
        },
        "started_at": _now(),
        "transport": getattr(transport, "name", "?"),
        "single_query": bool(single),
        "skin_model": skin_model,
    }

    tmp_dir = out_dir / "_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        photo, tmp = _inspect_input(path, max_side, tmp_dir)
        record["image"]["size"] = list(photo.image.size)
        record["framing"] = framing(photo)
        record["degrade"] = list(photo.degrade)
        if photo.rejected:
            record.update(status="rejected", error="no face")
        else:
            record["face"] = {"x": photo.face.x, "y": photo.face.y, "w": photo.face.w, "h": photo.face.h}
            result = _classify_with_retry(photo, transport, single)
            record["classification"] = {
                "ok": bool(result.ok),
                "error": result.error,
                "error_kind": result.error_kind,
                "double_checked": bool(result.double_checked),
                "elapsed": round(float(result.elapsed), 3),
                "raw_first": _jsonable(result.raw_first),
                "raw_second": _jsonable(result.raw_second),
            }
            if not result.ok:
                record.update(status="error", error=result.error or "classification failed")
            else:
                attrs = result.attributes
                record["classification"].update({
                    "values": dict(attrs.values),
                    "uncertain": list(result.uncertain),
                    "coerced": list(attrs.coerced),
                    "missing": list(attrs.missing),
                    "derived": list(attrs.derived),
                })
                seg = parsing.bottom_mask(photo.image) if parsing.parsing_on() else None
                observed = extract(photo, hair_bbox=result.hair_bbox_px, seg=seg)
                resolved_bottom, bottom_is_default = resolve_bottom_ex(attrs, observed)
                record["observed"] = {
                    "skin": observed.skin.hex,
                    "hair": observed.hair.hex,
                    "top": observed.top.hex,
                    "bottom": observed.bottom.hex,
                    "bottom_confident": bool(observed.bottom.confident),
                    "bottom_plausible": bool(observed.bottom_plausible),
                    "lower_body_seen": observed.lower_body_seen,
                    "lower_body_clothed": observed.lower_body_clothed,
                    "lower_body_bare": observed.lower_body_bare,
                    "fullbody": observed.fullbody,
                    "skirt_hem_rows": observed.skirt_hem_rows,
                    "stripe": observed.stripe,
                }
                record["resolved_bottom"] = resolved_bottom
                record["bottom_is_default"] = bool(bottom_is_default)
                bottom_needs_fallback = (
                    "bottom_garment" in attrs.missing
                    or "bottom_garment" in attrs.coerced
                    or attrs.get("bottom_garment") == "none"
                )
                record["bottom_source"] = (
                    "default_jeans" if bottom_is_default
                    else "dress" if resolved_bottom == "dress"
                    else "skirt" if resolved_bottom == "skirt"
                    else "measured" if bottom_needs_fallback and resolved_bottom in ("pants", "jeans")
                    else "vlm"
                )
                candidates = build(
                    observed, result, photo.degrade, skin_model, noise_level=1.0
                )
                if not candidates:
                    record.update(status="error", error="no candidates")
                else:
                    problems = [p for c in candidates for p in c.problems]
                    record["skins"] = []
                    for candidate in candidates:
                        name = f"skin_c{candidate.index}.png"
                        candidate.image.save(dest / name)
                        record["skins"].append(name)
                    record["skin_problems"] = problems
                    record["primary_skin"] = record["skins"][0]
                    if problems:
                        record.update(status="error", error="render validation failed")
                record["summary"] = summarize(attrs, result.uncertain)
    except Exception as exc:  # noqa: BLE001 — one bad photo must not kill the batch
        record.update(status="error", error=f"{type(exc).__name__}: {exc}")
    finally:
        if tmp is not None:
            try:
                tmp.unlink()
            except OSError:
                pass

    if render and record.get("status") == "ok" and render_out is not None:
        try:
            from .qarender import render_views

            primary = dest / record["primary_skin"]
            view_dir = render_out / rel
            rendered = render_views(primary, view_dir, model=skin_model)
            record["renders"] = {
                "front_right": "front_right.png",
                "back_right": "back_right.png",
                "contact_sheet": "contact_sheet.png",
            }
            record["compare"] = _comparison_sheet(path, view_dir, view_dir / "compare.png").name
            record["render_dir"] = str(view_dir.relative_to(render_out))
            del rendered
        except Exception as exc:  # noqa: BLE001
            record["render_error"] = f"{type(exc).__name__}: {exc}"

    record["finished_at"] = _now()
    result_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


def _comparison_sheet(original: Path, view_dir: Path, dest: Path) -> Path:
    """[original photo | front | back] side-by-side sheet for visual QA."""
    front = Image.open(view_dir / "front_right.png").convert("RGB")
    back = Image.open(view_dir / "back_right.png").convert("RGB")
    with Image.open(original) as source:
        photo = source.convert("RGB")
    scale = front.height / photo.height
    photo = photo.resize((max(1, int(photo.width * scale)), front.height), Image.LANCZOS)
    gap = 8
    label_h = 26
    width = photo.width + front.width + back.width + gap * 2
    sheet = Image.new("RGB", (width, front.height + label_h), (226, 232, 240))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default(size=15)
    except TypeError:
        font = ImageFont.load_default()
    x = 0
    for image, label in ((photo, "ORIGINAL"), (front, "FRONT-RIGHT"), (back, "BACK-RIGHT")):
        sheet.paste(image, (x, label_h))
        draw.text((x + 6, 6), label, fill=(38, 44, 52), font=font)
        x += image.width + gap
    sheet.save(dest)
    return dest


def write_manifest(out_dir: Path) -> dict:
    rows = []
    for result_path in sorted(out_dir.rglob("result.json")):
        try:
            rows.append(json.loads(result_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.get("status", "?")] = counts.get(row.get("status", "?"), 0) + 1
    manifest = {
        "generated_at": _now(),
        "count": len(rows),
        "status_counts": counts,
        "photos": rows,
    }
    (out_dir / "batch_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def build_selection(out_dir: Path, dest: Path | None = None) -> dict:
    """Group completed photos for QA: dress / skirt / upper-body fallback / measured / bare."""
    groups: dict[str, list[str]] = {
        "dress": [], "skirt": [], "upper_body_fallback": [],
        "measured_pants": [], "bare_legs": [],
    }
    rows = []
    for result_path in sorted(out_dir.rglob("result.json")):
        try:
            row = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if row.get("status") != "ok":
            continue
        rows.append(row)
        values = row.get("classification", {}).get("values", {})
        if values.get("top_garment") == "dress":
            groups["dress"].append(row["source"])
            continue
        if values.get("bottom_garment") == "skirt":
            groups["skirt"].append(row["source"])
            continue
        source = row.get("bottom_source")
        if source == "default_jeans":
            groups["upper_body_fallback"].append(row["source"])
        elif source == "measured":
            groups["measured_pants"].append(row["source"])
        elif row.get("resolved_bottom") == "none" and row.get("observed", {}).get("lower_body_bare"):
            groups["bare_legs"].append(row["source"])
    selection = {
        "generated_at": _now(),
        "counts": {k: len(v) for k, v in groups.items()},
        "groups": groups,
        "photos": [row["source"] for row in rows],
    }
    target = dest or (out_dir / "qa_selection.json")
    target.write_text(json.dumps(selection, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return selection


def run_batch(
    photodir: str | Path,
    out_dir: str | Path = DEFAULT_OUT,
    *,
    photo_list: str | Path | None = None,
    transport_name: str = "mock",
    model: str | None = None,
    single: bool = False,
    skin_model: str = DEFAULT_MODEL,
    max_side: int = 2048,
    render: bool = False,
    render_out: str | Path | None = None,
    sleep: float = 0.0,
    force: bool = False,
    limit: int | None = None,
    replay: bool = False,
) -> dict:
    root = Path(photodir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = discover(root, Path(photo_list) if photo_list else None)
    if limit:
        paths = paths[:limit]
    transport = None
    if replay:
        ok, detail = True, "replay from result.json"
    else:
        transport = get_transport(transport_name, model=model)
        ok, detail = transport.available()
    log_path = out / "run.log"

    def log(message: str) -> None:
        print(message, flush=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(message + "\n")

    log(f"batch start {_now()}  photos={len(paths)}  transport={'replay' if replay else transport_name} ({detail})  single={single}")
    if not ok:
        log("transport unavailable — abort")
        return {"error": "transport unavailable", "detail": detail, "count": 0}

    rendered_dir = Path(render_out) if render_out else Path(DEFAULT_RENDER_OUT)
    done = 0
    skipped = 0
    for index, path in enumerate(paths, 1):
        rel = relative_key(root, path)
        result_path = out / rel / "result.json"
        active = transport
        active_single = single
        if replay:
            if not result_path.is_file():
                skipped += 1
                log(f"[{index}/{len(paths)}] skip replay (no result) {rel}")
                continue
            try:
                existing = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                skipped += 1
                log(f"[{index}/{len(paths)}] skip replay (bad json) {rel}")
                continue
            first = existing.get("classification", {}).get("raw_first")
            if not first:
                skipped += 1
                log(f"[{index}/{len(paths)}] skip replay (no raw_first) {rel}")
                continue
            second = existing.get("classification", {}).get("raw_second")
            active = ReplayTransport(first=first, second=second)
            active_single = not bool(second)
        elif result_path.is_file() and not force:
            try:
                existing = json.loads(result_path.read_text(encoding="utf-8"))
                if existing.get("status") == "ok":
                    skipped += 1
                    log(f"[{index}/{len(paths)}] skip {rel}")
                    continue
            except (OSError, json.JSONDecodeError):
                pass
        started = time.monotonic()
        record = process_photo(
            path, root,
            out_dir=out, transport=active, single=active_single, skin_model=skin_model,
            max_side=max_side, render=render, render_out=rendered_dir,
        )
        elapsed = time.monotonic() - started
        done += 1
        log(f"[{index}/{len(paths)}] {record['status']:8s} {rel}  {elapsed:.1f}s"
            + (f"  ERROR {record['error']}" if record.get("error") else "")
            + (f"  RENDER {record.get('render_error')}" if record.get("render_error") else ""))
        if sleep and index < len(paths):
            time.sleep(sleep)

    manifest = write_manifest(out)
    selection = build_selection(out)
    log(f"batch done {_now()}  processed={done} skipped={skipped} statuses={manifest['status_counts']}")
    log(f"selection counts={selection['counts']}")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skinmaker.batch")
    parser.add_argument("--photos", default="out/people_photos_original")
    parser.add_argument("--photo-list", default=None, help="relative paths, one per line")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--transport", default="mock")
    parser.add_argument("--model", default=None)
    parser.add_argument("--skin-model", choices=("classic", "slim"), default=DEFAULT_MODEL)
    parser.add_argument("--single", action="store_true", help="one VLM query (no uncertainty/candidates)")
    parser.add_argument("--max-side", type=int, default=2048)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--render-out", default=DEFAULT_RENDER_OUT)
    parser.add_argument("--sleep", type=float, default=0.0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--replay", action="store_true", help="reprocess from stored VLM JSON (no API calls)")
    args = parser.parse_args(argv)
    try:
        result = run_batch(
            args.photos, args.out,
            photo_list=args.photo_list, transport_name=args.transport, model=args.model,
            single=args.single, skin_model=args.skin_model, max_side=args.max_side,
            render=args.render, render_out=args.render_out, sleep=args.sleep,
            force=args.force, limit=args.limit, replay=args.replay,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"batch failed: {exc}")
        return 1
    return 0 if result.get("count", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
