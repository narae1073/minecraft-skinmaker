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


app = FastAPI(title="skinmaker")


@app.get("/api/v1/health")
def health():
    transport = make_transport()
    ok, detail = transport.available()
    return {"status": "ok" if ok else "unavailable", "transport": detail}


@app.post("/api/v1/generate-skin")
async def generate_skin(file: UploadFile = File(...)):
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(400, "이미지 파일이 아님")
    with tempfile.NamedTemporaryFile(suffix=Path(file.filename or "up.jpg").suffix or ".jpg") as tmp:
        tmp.write(await file.read())
        tmp.flush()
        try:
            photo = inspect(tmp.name)
        except Exception as exc:
            raise HTTPException(400, f"이미지 읽기 실패: {type(exc).__name__}") from exc
    if photo.rejected:
        raise HTTPException(422, "얼굴을 찾지 못함")
    transport = make_transport()
    result = classify(photo, transport)
    if not result.ok:
        raise HTTPException(502, f"분류 실패: {result.error}")
    observed = extract(photo)
    candidates = build(observed, result, photo.degrade)
    if not candidates or not all(c.ok for c in candidates):
        raise HTTPException(500, "렌더 검증 실패")
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
