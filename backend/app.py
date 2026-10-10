"""웹 백엔드: Vite 프론트 + skinmaker 파이프라인 연결.

    set -a; source .env; set +a
    .venv/bin/python -m uvicorn backend.app:app --port 8000

계약 (frontend/src/App.jsx):
    POST /api/v1/generate-skin (multipart file)
    → {"status": "success", "data": {"skins": [url, ...], ...}}
"""
from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

from skinmaker.attributes import summarize
from skinmaker.candidates import build
from skinmaker.classify import classify
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


@app.get("/api/v1/health")
def health():
    transport = make_transport()
    ok, detail = transport.available()
    return {"status": "ok" if ok else "unavailable", "transport": detail}


@app.post("/api/v1/generate-skin")
async def generate_skin(file: UploadFile = File(...)):
    if not (file.content_type or "").startswith("image/"):
        fail(400, "not_image", "이미지 파일을 올려주세요.")
    with tempfile.NamedTemporaryFile(suffix=Path(file.filename or "up.jpg").suffix or ".jpg") as tmp:
        tmp.write(await file.read())
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
    observed = extract(photo)
    candidates = build(observed, result, photo.degrade)
    if not candidates or not all(c.ok for c in candidates):
        fail(500, "render_failed", "렌더 검증 실패. 같은 사진으로 다시 시도해주세요.")
    token = uuid.uuid4().hex[:12]
    urls = []
    for c in candidates:
        name = f"{token}_c{c.index}.png"
        c.image.save(STATIC_DIR / name)
        urls.append(f"/static/skins/{name}")
    return {
        "status": "success",
        "data": {
            "skins": urls,
            "summary": summarize(result.attributes, result.uncertain),
            "uncertain": list(result.uncertain),
        },
    }


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
