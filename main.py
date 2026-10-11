"""项目归档 + AI 问答 — FastAPI 入口。"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import db
from app.ai_client import detect_model
from app.routes import chat, projects, upload

app = FastAPI(title="项目归档 + AI 问答")


@app.on_event("startup")
def startup():
    db.init_db()
    try:
        detect_model()
    except Exception as exc:
        print(f"[ai] 模型探测失败：{exc}")


app.include_router(upload.router)
app.include_router(projects.router)
app.include_router(chat.router)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")
