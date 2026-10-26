"""웹 백엔드: Vite 프론트 + skinmaker 파이프라인 연결.

    set -a; source .env; set +a
    .venv/bin/python -m uvicorn backend.app:app --port 8000

계약 (frontend/src/App.jsx):
    POST /api/v1/generate-skin (multipart file)
    → {"status": "success", "data": {"skins": [url, ...], ...}}
"""
from __future__ import annotations

import dataclasses
import os
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.staticfiles import StaticFiles

from backend.limits import RateLimiter, client_ip, max_upload_bytes
from skinmaker.attributes import summarize
from skinmaker.candidates import build
from skinmaker.classify import classify
from skinmaker.render import resolve_bottom_ex
from skinmaker.colors import extract
from skinmaker.quality import inspect
from skinmaker.vlm import get_transport

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static" / "skins"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

TRANSPORT_ENV = "SKINMAKER_TRANSPORT"
MODEL_ENV = "SKINMAKER_MODEL"


def make_transport():
    """테스트에서 monkeypatch 로 교체한다."""
    name = os.environ.get(TRANSPORT_ENV, "gemini")
    return get_transport(name, model=os.environ.get(MODEL_ENV))


def fail(status_code: int, code: str, message: str):
    """프론트 에러 박스에 그대로 보여줄 구조화 본문."""
    raise HTTPException(status_code, {"status": "error", "code": code, "message": message})


def classify_error_status(message: str) -> tuple[int, str, str]:
    """일시 과부하(재시도 가능)와 확정 실패를 구분한다."""
    transient = ("429", "500", "502", "503", "504", "timeout", "Timeout", "temporarily")
    if any(t in message for t in transient):
        return 503, "overloaded", "AI 서버가 바빠요. 잠시 후 다시 눌러주세요."
    return 502, "classify_failed", f"분류 실패: {message[:200]}"


app = FastAPI(title="skinmaker")
_rate_limiter = RateLimiter()


@app.get("/api/v1/health")
def health():
    transport = make_transport()
    ok, detail = transport.available()
    return {"status": "ok" if ok else "unavailable", "transport": detail}


@app.post("/api/v1/generate-skin")
async def generate_skin(request: Request, file: UploadFile = File(...), noise_level: str = Form(None), steps: str = Form(None),
                        hair_source: str = Form(None), hair_symmetry: str = Form(None),
                        hair_overlay: str = Form(None)):
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
    # 머리 실루엣 스텐실 (Tier 0, 2026-10-15): 근원 머리 실루엣(mask, 기본)이냐 길이 규칙(rule)이냐.
    # 부재=기본, 모르는 값=400 (noise_level의 가비지 관례와 같은 축).
    def _hair_option(value, allowed: tuple[str, ...], default: str, name: str) -> str:
        if value is None:
            return default
        v = str(value).strip().lower()
        if v not in allowed:
            fail(400, "bad_hair_option", f"{name} 값은 {allowed} 중 하나여야 해요: {value!r}")
        return v

    hair_source = _hair_option(hair_source, ("mask", "rule"), "mask", "hair_source")
    hair_symmetry = _hair_option(hair_symmetry, ("symmetrized", "raw"), "symmetrized", "hair_symmetry")
    hair_overlay = _hair_option(hair_overlay, ("on", "off"), "on", "hair_overlay")
    # 처리 과정 시트 (설계 §12): 진위 규칙은 parsing_on 관례. 부재=생성 (기존 동작),
    # "0/false/off/no/빈값"=스킵 (설정 체크박스 기본 해제 → 웹이 명시 전송).
    want_steps = (steps is None) or (str(steps).strip().lower() not in ("0", "false", "off", "no", ""))
    raw = await file.read()
    # 공개 배포 가드: 파싱 전에 업로드 크기를 제한한다.
    if len(raw) > max_upload_bytes():
        fail(413, "too_large", f"이미지는 {max_upload_bytes() // (1024 * 1024)}MB 이하여야 해요.")
    with tempfile.NamedTemporaryFile(suffix=Path(file.filename or "up.jpg").suffix or ".jpg") as tmp:
        tmp.write(raw)
        tmp.flush()
        try:
            photo = inspect(tmp.name)
        except Exception as exc:
            fail(400, "unreadable", f"이미지를 읽지 못했어요: {type(exc).__name__}")
    if photo.rejected:
        fail(422, "no_face", "사진에서 얼굴을 찾지 못했어요. 정면 실사 얼굴 사진으로 다시 시도해주세요.")
    transport = make_transport()
    result = classify(photo, transport)
    if not result.ok:
        fail(*classify_error_status(result.error or ""))
    # 파서 마스크는 요청당 1회 — 색 추출과 마스크 패널이 같은 세그먼트를 공유한다 (설계 §12).
    from skinmaker import parsing as _parsing
    from skinmaker.debugview import steps_sheets

    seg = _parsing.bottom_mask(photo.image) if _parsing.parsing_on() else None
    observed = extract(photo, hair_bbox=result.hair_bbox_px, seg=seg,
                       hair_source=hair_source, hair_symmetry=hair_symmetry,
                       hair_overlay=hair_overlay == "on")
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
    candidates = build(observed, result, photo.degrade, noise_level=level)
    if not candidates or not all(c.ok for c in candidates):
        fail(500, "render_failed", "렌더 검증 실패. 같은 사진으로 다시 시도해주세요.")
    token = uuid.uuid4().hex[:12]
    input_name = f"input_{token}{Path(file.filename or 'up.jpg').suffix or '.jpg'}"
    (STATIC_DIR / input_name).write_bytes(raw)
    # 처리 과정 시트 (설계 §12): 스킨 목록과 분리된 steps/ 하위폴더. 끄면 아예 미생성.
    steps_urls = None
    if want_steps:
        STEPS_DIR = ROOT / "static" / "steps"  # /static 마운트 위치와 일치 (실앱 404 수정 2026-10-13)
        STEPS_DIR.mkdir(exist_ok=True)
        clean_sheet, full_sheet = steps_sheets(
            photo, candidates[0].image, "classic", observed, seg,
            # 스탬프는 요청이 아니라 실제 사용 모드 — 마스크 근거 실패면 rule로 기록 (진실 규칙)
            note="hair=" + ("mask+" + hair_symmetry if observed.hair_stencil else "rule") + " overlay=" + hair_overlay,
        )
        clean_sheet.convert("RGB").save(STEPS_DIR / f"{token}_steps.png")
        full_sheet.convert("RGB").save(STEPS_DIR / f"{token}_steps_full.png")
        steps_urls = {
            "clean": f"/static/steps/{token}_steps.png",
            "full": f"/static/steps/{token}_steps_full.png",
        }
    urls, flat_urls = [], []
    for c in candidates:
        name = f"{token}_c{c.index}.png"
        c.image.save(STATIC_DIR / name)
        flat_name = f"{token}_c{c.index}_flat.png"
        c.image_flat.save(STATIC_DIR / flat_name)  # Edit Skin 토글 OFF 변형 (설계 §5)
        urls.append(f"/static/skins/{name}")
        flat_urls.append(f"/static/skins/{flat_name}")
    return {
        "status": "success",
        "data": {
            "input": f"/static/skins/{input_name}",
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
            "hair_source": hair_source,
            "hair_symmetry": hair_symmetry,
            "hair_overlay": hair_overlay,
            "steps": steps_urls,
        },
    }


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
