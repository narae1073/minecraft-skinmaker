"""웹 백엔드: Vite 프론트 + skinmaker 파이프라인 연결.

    set -a; source .env; set +a
    .venv/bin/python -m uvicorn backend.app:app --port 8000

계약 (frontend/src/App.jsx):
    POST /api/v1/generate-skin (multipart file)
    → {"status": "success", "data": {"skins": [url, ...], ...}}
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import time
import os
import sys
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend import jobs as JOBS
from skinmaker import job_codec as JC
from backend.limits import RateLimiter, client_ip, max_upload_bytes
from skinmaker.attributes import summarize
from skinmaker.candidates import build
from skinmaker.classify import classify
from skinmaker.render import resolve_bottom_ex
from skinmaker.colors import ColorSample, extract
from skinmaker.quality import FaceBox, inspect
from skinmaker.vlm import get_transport

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static" / "skins"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


def load_env_file(path: Path | None = None, *, enabled: bool | None = None) -> bool:
    """실서버에서 저장소 루트 `.env` 를 읽는다 (실제 환경변수가 우선).

    `uvicorn backend.app:app` 만으로 mock 전송 계층/키가 적용되게 한다.
    pytest 중에는 로컬 `.env` 가 스위트 환경을 바꾸지 않도록 건너뛴다.
    반환값은 실제로 파일을 읽었는지 여부다 (테스트용).
    """
    if enabled is None:
        enabled = "pytest" not in sys.modules
    if not enabled:
        return False
    target = Path(path) if path is not None else REPO_ROOT / ".env"
    if not target.is_file():
        return False
    try:
        from dotenv import load_dotenv
    except ImportError:
        return False
    try:
        load_dotenv(target, override=False)
    except OSError:
        return False
    return True


load_env_file()

TRANSPORT_ENV = "SKINMAKER_TRANSPORT"
MODEL_ENV = "SKINMAKER_MODEL"
SKIN_MODELS = ("classic", "slim")


def make_transport():
    """테스트에서 monkeypatch 로 교체한다."""
    name = os.environ.get(TRANSPORT_ENV, "gemini")
    timeout = float(os.environ.get("SKINMAKER_VLM_TIMEOUT", "10"))
    return get_transport(name, model=os.environ.get(MODEL_ENV), timeout=timeout)


def fail(status_code: int, code: str, message: str, extra: dict | None = None):
    """프론트 에러 박스에 그대로 보여줄 구조화 본문."""
    payload = {"status": "error", "code": code, "message": message}
    if extra:
        payload.update(extra)
    raise HTTPException(status_code, payload)


async def _await_or_cancel(request: Request, func, *args, **kwargs):
    """Run a blocking pipeline stage off the event loop; stop if the client is gone."""
    if await request.is_disconnected():
        raise HTTPException(499, {"status": "error", "code": "client_closed",
                                  "message": "요청이 취소되었어요."})
    result = await asyncio.to_thread(func, *args, **kwargs)
    if await request.is_disconnected():
        raise HTTPException(499, {"status": "error", "code": "client_closed",
                                  "message": "요청이 취소되었어요."})
    return result


def classify_error_status(message: str) -> tuple[int, str, str]:
    """일시 과부하(재시도 가능)와 확정 실패를 구분한다."""
    transient = ("429", "500", "502", "503", "504", "timeout", "Timeout", "temporarily")
    if any(t in message for t in transient):
        return 503, "overloaded", "AI 서버가 바빠요. 잠시 후 다시 눌러주세요."
    return 502, "classify_failed", f"분류 실패: {message[:200]}"


def resolve_skin_model(value: str | None) -> str:
    """스킨 체형 (classic 4px 팔 / slim 3px 팔). 부재=classic, 모르는 값=400."""
    if value is None:
        return "classic"
    v = str(value).strip().lower()
    if v not in SKIN_MODELS:
        fail(400, "bad_model", f"skin_model 값은 {SKIN_MODELS} 중 하나여야 해요: {value!r}")
    return v


app = FastAPI(title="skinmaker")
_rate_limiter = RateLimiter()


@app.get("/api/v1/health")
def health():
    transport = make_transport()
    # health 는 앱 생존 확인 경로다. available() 은 OpenRouter/Ollama 에서
    # 외부 네트워크를 타므로, 설정만 보는 configured() 를 쓴다.
    ok, detail = transport.configured()
    return {"status": "ok" if ok else "unavailable", "transport": detail}


@app.post("/api/v1/generate-skin")
async def generate_skin(request: Request, response: Response, file: UploadFile = File(...), noise_level: str = Form(None), steps: str = Form(None),
                        hair_overlay: str = Form(None), skin_model: str = Form(None), hair_color: str = Form(None),
                        crop: str = Form(None)):
    # The owner cookie identifies the browser that generated a skin (edit access).
    secret = JOBS.owner_secret_from_request(request)
    is_new = secret is None
    if is_new:
        secret = JOBS.new_owner_secret()
    result = await _start(request, file, noise_level, steps, hair_overlay, skin_model, hair_color, crop,
                          owner_hash=JOBS.owner_hash(secret))
    if is_new:
        cookie = dict(key=JOBS.OWNER_COOKIE, value=secret, httponly=True, samesite="strict",
                      max_age=60 * 60 * 24 * 365, path="/",
                      secure=_is_https(request))
        if isinstance(result, StreamingResponse):
            result.set_cookie(**cookie)
        else:
            response.set_cookie(**cookie)
    return result


def _is_https(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


async def _start(request, file, noise_level, steps, hair_overlay, skin_model, hair_color, crop, *, owner_hash=None):
    if "text/event-stream" not in (request.headers.get("accept") or ""):
        return await _pipeline(request, file, noise_level, steps, hair_overlay, skin_model, hair_color, crop,
                               owner_hash=owner_hash)
    queue = asyncio.Queue()

    async def on_stage(item):
        await queue.put(item)

    task = asyncio.create_task(_pipeline(
        request, file, noise_level, steps, hair_overlay, skin_model, hair_color, crop, on_stage=on_stage,
        owner_hash=owner_hash))

    async def gen():
        while not task.done():
            try:
                item = await asyncio.wait_for(queue.get(), timeout=0.2)
                yield "event: progress\ndata: " + json.dumps(item, ensure_ascii=False) + "\n\n"
            except asyncio.TimeoutError:
                continue
        while not queue.empty():
            item = queue.get_nowait()
            yield "event: progress\ndata: " + json.dumps(item, ensure_ascii=False) + "\n\n"
        if task.exception() is not None:
            exc = task.exception()
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            yield "event: error\ndata: " + json.dumps({"message": detail}, ensure_ascii=False) + "\n\n"
        else:
            yield "event: result\ndata: " + json.dumps(task.result(), ensure_ascii=False) + "\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def _pipeline(request: Request, file: UploadFile = File(...), noise_level: str = Form(None), steps: str = Form(None),
                        hair_overlay: str = Form(None), skin_model: str = Form(None), hair_color: str = Form(None),
                        crop: str = Form(None), *, on_stage=None, owner_hash=None):
    timings = {}
    async def stage(name, pct, label):
        if on_stage is not None:
            await on_stage({"stage": name, "pct": pct, "label": label})
    t0 = time.perf_counter()
    # 공개 배포 가드 (로그인 없음): IP당 분당 요청 제한.
    if not _rate_limiter.allow(client_ip(request)):
        fail(429, "rate_limited", "요청이 너무 잦아요. 잠시 후 다시 시도해주세요.")
    if not (file.content_type or "").startswith("image/"):
        fail(400, "not_image", "이미지 파일을 올려주세요.")
    # 노이즈 세기 (설계 §9): 부재=1.0, 가비지=400, 범위 밖 숫자는 [0,1] 클램프.
    level = 1.0
    if noise_level is not None:
        try:
            level = float(noise_level)
        except (TypeError, ValueError):
            fail(400, "bad_noise_level", f"noise_level은 숫자여야 해요: {noise_level!r}")
        level = min(1.0, max(0.0, level))
    # 머리 오버레이 옵션: 부재=기본, 모르는 값=400 (noise_level의 가비지 관례와 같은 축).
    def _hair_option(value, allowed: tuple[str, ...], default: str, name: str) -> str:
        if value is None:
            return default
        v = str(value).strip().lower()
        if v not in allowed:
            fail(400, "bad_hair_option", f"{name} 값은 {allowed} 중 하나여야 해요: {value!r}")
        return v

    hair_overlay = _hair_option(hair_overlay, ("on", "off"), "on", "hair_overlay")
    skin_model = resolve_skin_model(skin_model)
    crop_box = None
    if crop:
        try:
            data = json.loads(crop)
            if isinstance(data, dict):
                x, y, w, h = (int(round(float(data[k]))) for k in ("x", "y", "w", "h"))
            elif isinstance(data, (list, tuple)) and len(data) == 4:
                x, y, w, h = (int(round(float(v))) for v in data)
            else:
                raise ValueError("bad crop shape")
            if w <= 0 or h <= 0:
                raise ValueError("empty crop")
            crop_box = FaceBox(x, y, w, h)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            fail(400, "bad_crop", "crop은 {x,y,w,h} 픽셀 좌표여야 해요.")
    # 처리 과정 시트 (설계 §12): 진위 규칙은 parsing_on 관례. 부재=생성 (기존 동작),
    # "0/false/off/no/빈값"=스킵 (설정 체크박스 기본 해제 → 웹이 명시 전송).
    want_steps = (steps is None) or (str(steps).strip().lower() not in ("0", "false", "off", "no", ""))
    raw = await file.read()
    # 공개 배포 가드: 파싱 전에 업로드 크기를 제한한다.
    if len(raw) > max_upload_bytes():
        fail(413, "too_large", f"이미지는 {max_upload_bytes() // (1024 * 1024)}MB 이하여야 해요.")
    # The upload is already in memory. inspect() reads the bytes directly, so
    # the app never creates its own temporary copy of the original photo.
    try:
        await stage("inspect", 8, "인물과 얼굴을 찾는 중이에요")
        _t = time.perf_counter()
        photo = await _await_or_cancel(request, inspect, raw, crop=crop_box)
        timings["inspect"] = round(time.perf_counter() - _t, 3)
    except Exception as exc:
        fail(400, "unreadable", f"이미지를 읽지 못했어요: {type(exc).__name__}")
    if photo.rejected:
        fail(422, "no_face", "사진에서 얼굴을 찾지 못했어요. 정면 실사 얼굴 사진으로 다시 시도해주세요.",
             extra={"can_crop": True, "image_size": list(photo.image.size), "source": photo.source})
    await stage("classify", 30, "의상을 분석하는 중이에요")
    _t = time.perf_counter()
    transport = make_transport()
    result = await _await_or_cancel(request, classify, photo, transport)
    timings["classify"] = round(time.perf_counter() - _t, 3)
    if not result.ok:
        # 자격증명/설정 누락은 재시도로 풀리지 않는다 — 502 분류 실패와 구분한다.
        if result.error_kind == "transport":
            fail(503, "ai_unavailable", "AI 연결이 설정되지 않았어요. 잠시 후 다시 시도해주세요.")
        fail(*classify_error_status(result.error or ""))
    # 파서 마스크는 요청당 1회 — 색 추출과 마스크 패널이 같은 세그먼트를 공유한다 (설계 §12).
    from skinmaker import parsing as _parsing
    from skinmaker.debugview import steps_sheets

    await stage("segment", 55, "옷 영역을 나누는 중이에요")
    _t = time.perf_counter()
    seg = (await _await_or_cancel(request, _parsing.bottom_mask, photo.image)) if _parsing.parsing_on() else None
    timings["segment"] = round(time.perf_counter() - _t, 3)
    await stage("extract", 68, "색을 추출하는 중이에요")
    _t = time.perf_counter()
    observed = await _await_or_cancel(
        request, extract, photo, hair_bbox=result.hair_bbox_px, seg=seg,
        hair_overlay=hair_overlay == "on")
    timings["extract"] = round(time.perf_counter() - _t, 3)
    # Manual hair-colour override (2026-11-02): the user's notes 00/02/06 are
    # source-limited (no gold in the visible hair); the UI can set the colour.
    if hair_color:
        import re as _re
        hc = str(hair_color).strip().lower()
        if not _re.fullmatch(r"#[0-9a-f]{6}", hc):
            fail(400, "bad_hair_color", f"hair_color는 #rrggbb 형식이어야 해요: {hair_color!r}")
        rgb = (int(hc[1:3], 16), int(hc[3:5], 16), int(hc[5:7], 16))
        observed = dataclasses.replace(
            observed, hair=ColorSample(hc, 1.0, True, rgb, 1000)
        )
    # 하체 미관측 jeans 기본 (설계 §10): 요약이 텍스처와 어긋나지 않게 같은
    # resolve_bottom_ex 결정을 요약에도 반영한다 (derived 표기).
    resolved_bottom, bottom_is_default = resolve_bottom_ex(result.attributes, observed)
    sum_attrs = result.attributes
    if bottom_is_default and resolved_bottom != result.attributes.get("bottom_garment"):
        values = dict(result.attributes.values)
        values["bottom_garment"] = resolved_bottom
        sum_attrs = dataclasses.replace(
            result.attributes, values=values,
            derived=(*result.attributes.derived, "bottom_garment=jeans (하체 미관측 기본)"),
        )
    await stage("render", 80, "스킨을 그리는 중이에요")
    _t = time.perf_counter()
    candidates = await _await_or_cancel(request, build, observed, result, photo.degrade, model=skin_model, noise_level=level)
    timings["render"] = round(time.perf_counter() - _t, 3)
    if not candidates or not all(c.ok for c in candidates):
        fail(500, "render_failed", "렌더 검증 실패. 같은 사진으로 다시 시도해주세요.")
    token = uuid.uuid4().hex[:12]
    # 처리 과정 시트 (설계 §12): 스킨 목록과 분리된 steps/ 하위폴더. 끄면 아예 미생성.
    steps_urls = None
    await stage("saving", 88, "이미지를 저장하는 중이에요")
    if want_steps:
        STEPS_DIR = ROOT / "static" / "steps"  # /static 마운트 위치와 일치 (실앱 404 수정 2026-10-13)
        STEPS_DIR.mkdir(exist_ok=True)
        clean_sheet, full_sheet = await _await_or_cancel(
            request, steps_sheets,
            photo, candidates[0].image, skin_model, observed, seg,
            # 스탬프는 요청이 아니라 실제 사용 모드 — 마스크 근거 실패면 rule로 기록 (진실 규칙)
            note="hair=" + ("mask+symmetrized" if observed.hair_stencil else "rule") + " overlay=" + hair_overlay,
            privacy=True,  # public sheet: no source-photo pixels (2026-11-05)
        )
        clean_sheet.convert("RGB").save(STEPS_DIR / f"{token}_steps.png")
        full_sheet.convert("RGB").save(STEPS_DIR / f"{token}_steps_full.png")
        steps_urls = {
            "clean": f"/static/steps/{token}_steps.png",
            "full": f"/static/steps/{token}_steps_full.png",
        }
    await stage("steps", 95, "마무리하는 중이에요")
    urls, flat_urls = [], []
    for c in candidates:
        name = f"{token}_c{c.index}.png"
        c.image.save(STATIC_DIR / name)
        flat_name = f"{token}_c{c.index}_flat.png"
        c.image_flat.save(STATIC_DIR / flat_name)  # Edit Skin 토글 OFF 변형 (설계 §5)
        urls.append(f"/static/skins/{name}")
        flat_urls.append(f"/static/skins/{flat_name}")
    if owner_hash is not None:
        JOBS.create_record(token, owner_hash, observed, candidates, model=skin_model,
                           noise_level=level, degrade=tuple(photo.degrade))
    await stage("done", 100, "완료")
    timings["total"] = round(time.perf_counter() - t0, 3)
    return {
        "status": "success",
        "data": {
            "job": {"id": token, "editable": owner_hash is not None},
            "skins": urls,
            "skins_flat": flat_urls,
            "summary": summarize(sum_attrs, result.uncertain),
            "uncertain": list(result.uncertain),
            # 분류 카테고리 구조화 JSON (설계 §11) — 웹이 표로 렌더한다.
            "attributes": {
                "values": dict(sum_attrs.values),
                "uncertain": list(result.uncertain),
                "derived": list(sum_attrs.derived),
                "coerced": list(sum_attrs.coerced),
            },
            "candidates": [
                {"index": c.index, "varied": c.varied} for c in candidates
            ],
            "noise_level": level,
            "skin_model": skin_model,
            "hair_overlay": hair_overlay,
            "steps": steps_urls,
            "timings": timings,
        },
    }


# ---- owner-only skin jobs (per-skin mask edits) --------------------------------
_render_limiter = RateLimiter(limit=20)


def _job_for_owner(request: Request, token: str) -> dict:
    record = JOBS.load_record(token)
    if record is None:
        fail(404, "not_found", "그 스킨을 찾을 수 없어요.")
    if not JOBS.is_owner(record, request):
        fail(403, "forbidden", "이 스킨은 만든 브라우저에서만 편집할 수 있어요.")
    return record


def _require_json(request: Request) -> None:
    if not (request.headers.get("content-type") or "").startswith("application/json"):
        fail(415, "bad_content_type", "JSON 요청만 받아요.")


@app.get("/api/v1/jobs/{token}")
def job_info(token: str, request: Request):
    record = _job_for_owner(request, token)
    return {"status": "success", "data": {
        "id": record["id"], "model": record["model"], "revision": record["revision"],
        "candidates": [{"index": c["index"], "varied": c["varied"],
                        "attributes": JC.encode(c["attributes"])["values"]} for c in record["candidates"]],
    }}


@app.get("/api/v1/jobs/{token}/overlay")
def job_overlay(token: str, request: Request):
    record = _job_for_owner(request, token)
    return JSONResponse({"masks": record.get("overlay", {}), "revision": record["revision"]},
                        headers={"Cache-Control": "no-store"})


def _candidate_index(value) -> int:
    try:
        return int(value if value is not None else 1)
    except (TypeError, ValueError):
        fail(400, "bad_index", "index 는 정수여야 해요.")


@app.put("/api/v1/jobs/{token}/overlay")
async def job_overlay_put(token: str, request: Request):
    """Save the editor's masks. Only entries that differ from the baseline are stored."""
    _require_json(request)
    record = _job_for_owner(request, token)
    body = await request.json()
    masks = body.get("masks") if isinstance(body, dict) else None
    errors = JOBS.validate_masks(masks, JOBS.EDITOR_BODY_MAX_BYTES)
    if errors:
        fail(400, "bad_overlay", "; ".join(errors[:5]))
    index = _candidate_index(body.get("index") if isinstance(body, dict) else None)
    if JOBS.candidate(record, index) is None:
        fail(404, "not_found", "그 후보가 없어요.")
    record["overlay"] = JOBS.diff_against_baseline(masks, record, index)
    record["revision"] = int(record.get("revision", 0)) + 1
    JOBS.save_record(record)
    return {"ok": True, "revision": record["revision"], "changed": sorted(record["overlay"])}


@app.post("/api/v1/jobs/{token}/attributes")
async def job_attributes(token: str, request: Request):
    """Change this skin's headwear (none / cap). Only this skin is affected."""
    _require_json(request)
    record = _job_for_owner(request, token)
    body = await request.json()
    value = body.get("headwear") if isinstance(body, dict) else None
    color = body.get("hat_color") if isinstance(body, dict) else None
    if value not in JOBS.HEADWEAR_CHOICES:
        fail(400, "bad_headwear", "headwear 는 none, cap, beanie 중 하나여야 해요.")
    try:
        JOBS.set_headwear(record, value, color)
    except ValueError:
        fail(400, "bad_hat_color", "hat_color 는 #rrggbb 형식이어야 해요.")
    record["revision"] = int(record.get("revision", 0)) + 1
    JOBS.save_record(record)
    return {"ok": True, "headwear": value, "revision": record["revision"]}


@app.get("/api/v1/jobs/{token}/editor")
def job_editor(token: str, request: Request, index: int = 1, baseline: int = 0):
    """Everything the per-skin editor needs. ``baseline=1`` returns the procedural
    starting point (the reset target) instead of the job's current masks."""
    record = _job_for_owner(request, token)
    index = _candidate_index(index)
    if JOBS.candidate(record, index) is None:
        fail(404, "not_found", "그 후보가 없어요.")
    payload = JOBS.editor_payload(record, index)
    if baseline:
        payload["masks"] = JOBS.baseline_masks(record, index)
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


@app.get("/api/v1/jobs/{token}/seed")
def job_seed(token: str, request: Request, key: str = "", value: str = "", index: int = 1):
    from skinmaker.attribute_seeds import MASKABLE
    record = _job_for_owner(request, token)
    index = _candidate_index(index)
    if key not in MASKABLE or value not in MASKABLE[key]:
        fail(400, "bad_key", "알 수 없는 마스크 키예요.")
    entry = JOBS.baseline_masks(record, index)[f"{key}.{value}"]
    return JSONResponse({"key": key, "value": value, "mask": entry}, headers={"Cache-Control": "no-store"})


@app.post("/api/v1/jobs/{token}/preview")
async def job_preview(token: str, request: Request):
    """Render the candidate with the editor's current masks, without saving anything.
    Returns the PNG as a data URL so the editor can show it at once."""
    import base64
    _require_json(request)
    record = _job_for_owner(request, token)
    if not _render_limiter.allow(client_ip(request)):
        fail(429, "rate_limited", "잠시 후 다시 시도해주세요.")
    body = await request.json()
    masks = body.get("masks") if isinstance(body, dict) else None
    errors = JOBS.validate_masks(masks, JOBS.EDITOR_BODY_MAX_BYTES)
    if errors:
        fail(400, "bad_masks", "; ".join(errors[:5]))
    index = _candidate_index(body.get("index"))
    if JOBS.candidate(record, index) is None:
        fail(404, "not_found", "그 후보가 없어요.")
    png, problems = await asyncio.to_thread(JOBS.preview_png, record, index, masks)
    return {"skin": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
            "mask": None, "key": "", "value": "", "mode": "final", "effective": {},
            "warnings": [], "coerced": [], "derived": [], "problems": problems}


@app.post("/api/v1/jobs/{token}/render")
async def job_render(token: str, request: Request):
    _require_json(request)
    record = _job_for_owner(request, token)
    if not _render_limiter.allow(client_ip(request)):
        fail(429, "rate_limited", "잠시 후 다시 시도해주세요.")
    body = await request.json()
    try:
        index = int(body.get("index", 1))
    except (TypeError, ValueError, AttributeError):
        fail(400, "bad_index", "index 는 정수여야 해요.")
    if JOBS.candidate(record, index) is None:
        fail(404, "not_found", "그 후보가 없어요.")
    image, flat, problems = await asyncio.to_thread(JOBS.render_candidate, record, index)
    rev = int(record.get("revision", 0))
    name = f"{token}_e{rev}_c{index}.png"
    flat_name = f"{token}_e{rev}_c{index}_flat.png"
    image.save(STATIC_DIR / name)
    flat.save(STATIC_DIR / flat_name)
    return {"skin": f"/static/skins/{name}", "skin_flat": f"/static/skins/{flat_name}",
            "revision": rev, "problems": problems}


# ---- per-skin editor page ------------------------------------------------------
EDITOR_DIR = REPO_ROOT / "tools" / "mask_editor"
EDITOR_LIB_FILES = {"app.js", "viewer.js", "atlas.js"}
EDITOR_VENDOR_FILES = {"three.core.js", "three.module.js", "OrbitControls.js"}
_EDITOR_CSS = """
body[data-job] #comboPanel, body[data-job] #srcBtn, body[data-job] .group:has(#photoInput) { display: none !important; }
"""


@app.get("/edit/{token}")
def job_editor_page(token: str, request: Request):
    record = JOBS.load_record(token)
    if record is None or not JOBS.is_owner(record, request):
        return HTMLResponse("<!doctype html><meta charset=utf-8><p>이 스킨은 만든 브라우저에서만 편집할 수 있어요.</p>",
                            status_code=403)
    html = (EDITOR_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace("/static/", "/edit/lib/")
    # Job mode saves to this skin's overlay, not the developer draft file.
    html = html.replace(
        "저장은 <code>out/mask_editor/attribute_masks.json</code>",
        "저장은 이 스킨에만 적용됩니다",
    )
    html = html.replace("<body>", f'<body data-job="{token}">', 1)
    html = html.replace('<script type="module"',
                        f'<style>{_EDITOR_CSS}</style>\n<script>window.MASK_EDITOR_JOB = "{token}";</script>\n<script type="module"', 1)
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@app.get("/edit/lib/{name:path}")
def job_editor_asset(name: str):
    """Only the editor's own scripts and the vendored three.js are public."""
    if name in EDITOR_LIB_FILES:
        path = EDITOR_DIR / name
    elif name.startswith("vendor/") and name.split("/", 1)[1] in EDITOR_VENDOR_FILES:
        path = EDITOR_DIR / name
    else:
        fail(404, "not_found", "없는 파일이에요.")
    if not path.is_file():
        fail(404, "not_found", "없는 파일이에요.")
    return FileResponse(path, headers={"Cache-Control": "public, max-age=3600"})


def mount_frontend(application: FastAPI, dist: Path = FRONTEND_DIST) -> None:
    """dist 가 없어도 마운트한다. 빌드 전에는 404, 빌드 후에는 재시작 없이 서빙."""
    dist.mkdir(parents=True, exist_ok=True)
    application.mount("/", StaticFiles(directory=dist, html=True), name="frontend")


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
mount_frontend(app)
