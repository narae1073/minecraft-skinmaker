"""VLM similarity scoring for generated skins (2026-10-28).

Scores each batch result against its original photo using the QA comparison
sheet ([original | front-right | back-right]) and writes a worst→best ranking.

    python -m skinmaker.score --batch out/qa_full_final \
        --renders out/qa_render_full_all --out out/qa_scores.json \
        --transport gemini --jobs 3

Categories: head, top, bottom, overall (1–10). The tool is resumable: sources
already present in the output are skipped unless --force.
"""
from __future__ import annotations

import argparse
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from .vlm import get_transport

CATEGORIES = ("head", "top", "bottom", "overall")
PROMPT = """You are evaluating a Minecraft skin generator.

The image is a side-by-side sheet:
- left: the original human photo
- middle: the generated skin, front-right 3D render
- right: the generated skin, back-right 3D render

Score each category from 1 to 10:
- head: face placement, hair shape/colour, skin tone
- top: upper garment type, colour, pattern, visible structure (collar/zipper/buttons)
- bottom: lower garment type, colour, hem length, leg coverage
- overall: outfit/vibe resemblance as a whole

10 = nearly indistinguishable at this resolution; 5 = clearly recognisable but
with obvious misses; 1 = wrong person/outfit. Do not reward detail that a
64x64 skin cannot carry. Be critical but fair.

Return JSON only: {"head": int, "top": int, "bottom": int, "overall": int,
"issues": ["short issue", ...]}.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "head": {"type": "integer"},
        "top": {"type": "integer"},
        "bottom": {"type": "integer"},
        "overall": {"type": "integer"},
        "issues": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["head", "top", "bottom", "overall"],
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def discover(batch_root: Path, renders_root: Path) -> list[dict]:
    """Completed results that have a comparison sheet, sorted by source."""
    out = []
    for result_path in sorted(Path(batch_root).rglob("result.json")):
        try:
            row = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if row.get("status") != "ok":
            continue
        source = row.get("source")
        compare = Path(renders_root) / source / "compare.png"
        if not source or not compare.is_file():
            continue
        values = row.get("classification", {}).get("values", {})
        out.append({
            "source": source,
            "compare": str(compare),
            "pattern": values.get("pattern"),
            "top_garment": values.get("top_garment"),
            "bottom_garment": values.get("bottom_garment"),
        })
    return out


def parse_scores(raw: dict | None) -> dict | None:
    """Validate/clamp the model output. Missing categories are a failure."""
    if not isinstance(raw, dict):
        return None
    parsed = {}
    for name in CATEGORIES:
        value = raw.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        parsed[name] = max(1, min(10, int(round(value))))
    issues = raw.get("issues") or []
    if not isinstance(issues, list):
        issues = [str(issues)]
    parsed["issues"] = [str(item)[:200] for item in issues[:3]]
    parsed["mean"] = round(sum(parsed[name] for name in CATEGORIES) / len(CATEGORIES), 2)
    return parsed


def _score_once(transport, image_path: str) -> dict | None:
    with Image.open(image_path) as image:
        raw = transport.complete(image.convert("RGB"), PROMPT, SCHEMA)
    return parse_scores(raw)


def score_photo(transport, item: dict, repeat: int = 1, retries: int = 2) -> dict:
    """One photo, with retries and optional repeat/median."""
    last_error = None
    results = []
    for _ in range(max(1, repeat)):
        for attempt in range(retries + 1):
            try:
                got = _score_once(transport, item["compare"])
            except Exception as exc:  # noqa: BLE001 — transport failures are data
                got = None
                last_error = f"{type(exc).__name__}: {exc}"
            if got is not None:
                results.append(got)
                break
            last_error = getattr(transport, "last_error", None) or last_error or "no scores"
            time.sleep(1.0 * (attempt + 1))
    if not results:
        return {**item, "status": "error", "error": last_error or "no scores"}
    if len(results) == 1:
        payload = results[0]
    else:
        payload = {
            name: sorted(r[name] for r in results)[len(results) // 2]
            for name in CATEGORIES
        }
        payload["mean"] = round(sum(payload[name] for name in CATEGORIES) / len(CATEGORIES), 2)
        payload["issues"] = results[-1].get("issues", [])
    return {**item, "status": "ok", **payload}


def run_scoring(
    batch_root: str | Path,
    renders_root: str | Path,
    out_path: str | Path = "out/qa_scores.json",
    *,
    transport=None,
    transport_name: str = "gemini",
    model: str | None = None,
    only: list[str] | None = None,
    limit: int | None = None,
    jobs: int = 1,
    sleep: float = 0.0,
    repeat: int = 1,
    force: bool = False,
) -> dict:
    batch = Path(batch_root)
    renders = Path(renders_root)
    out = Path(out_path)
    items = discover(batch, renders)
    if only:
        wanted = {Path(p).as_posix().lstrip("./") for p in only}
        items = [item for item in items if item["source"] in wanted or Path(item["source"]).name in wanted]
    if limit:
        items = items[:limit]
    if not items:
        raise ValueError("no scoreable photos (need result.json + compare.png)")

    previous: dict[str, dict] = {}
    if out.is_file() and not force:
        try:
            old = json.loads(out.read_text(encoding="utf-8"))
            previous = {row["source"]: row for row in old.get("scores", [])}
        except (OSError, json.JSONDecodeError):
            previous = {}

    todo = [item for item in items if item["source"] not in previous]
    if transport is None:
        transport = get_transport(transport_name, model=model)
        ok, detail = transport.available()
        if not ok:
            raise RuntimeError(f"transport unavailable: {detail}")
    name = getattr(transport, "name", transport_name)
    print(f"scoring {len(todo)} photos ({len(items) - len(todo)} cached) with {name}", flush=True)

    scores = dict(previous)
    lock = threading.Lock()
    done = 0

    def work(item):
        nonlocal done
        result = score_photo(transport, item, repeat=repeat)
        with lock:
            scores[item["source"]] = result
            done += 1
            print(f"[{done}/{len(todo)}] {result['status']:5s} {item['source']} "
                  f"mean={result.get('mean', '-')} issues={result.get('issues', [])[:1]}", flush=True)
        if sleep:
            time.sleep(sleep)
        return result

    if jobs <= 1:
        for item in todo:
            work(item)
    else:
        with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
            futures = [pool.submit(work, item) for item in todo]
            for future in as_completed(futures):
                future.result()

    ordered = list(scores.values())
    ranked = sorted(ordered, key=lambda row: (row.get("mean", 99), row.get("overall", 99), row["source"]))
    report = {
        "generated_at": _now(),
        "model": getattr(transport, "model", model or name),
        "count": len(ordered),
        "scored": sum(1 for row in ordered if row.get("status") == "ok"),
        "errors": sum(1 for row in ordered if row.get("status") != "ok"),
        "categories": list(CATEGORIES),
        "ranking": [row["source"] for row in ranked],
        "scores": ranked,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out} ({report['scored']} scored, {report['errors']} errors)", flush=True)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skinmaker.score")
    parser.add_argument("--batch", default="out/qa_full_final")
    parser.add_argument("--renders", default="out/qa_render_full_all")
    parser.add_argument("--out", default="out/qa_scores.json")
    parser.add_argument("--transport", default="gemini")
    parser.add_argument("--model", default=None)
    parser.add_argument("--only", action="append", default=None, help="source path (repeatable)")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--sleep", type=float, default=0.0)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        run_scoring(
            args.batch, args.renders, args.out,
            transport_name=args.transport, model=args.model, only=args.only,
            limit=args.limit, jobs=args.jobs, sleep=args.sleep,
            repeat=args.repeat, force=args.force,
        )
    except (ValueError, RuntimeError) as exc:
        print(f"scoring failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
