"""上传接口：保存文件 → 解析文本 → AI 识别归档到项目 → 分块入库。"""
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from .. import db
from ..ai_client import classify_upload
from ..parser import UnsupportedFile, chunk_text, extract_text, preview_of

router = APIRouter()

MAX_SIZE = 20 * 1024 * 1024  # 20MB


@router.post("/api/upload")
async def upload(
    files: list[UploadFile] = File(...),
    project_id: int | None = Form(None),
):
    """上传文件。带 project_id 时直接归入该项目；否则走 AI 自动识别归属。"""
    results = []
    for f in files:
        try:
            results.append(await _process_one(f, project_id))
        except UnsupportedFile as exc:
            results.append({"filename": f.filename, "status": "error", "error": str(exc)})
        except Exception as exc:
            results.append({"filename": f.filename, "status": "error", "error": f"处理失败：{exc}"})
    return {"results": results}


def _fix_filename(name: str) -> str:
    """修复 multipart 文件名被按 latin-1 解码造成的中文乱码。"""
    for enc in ("utf-8", "gbk"):
        try:
            return name.encode("latin-1").decode(enc)
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return name


async def _process_one(f: UploadFile, project_id: int | None = None) -> dict:
    filename = Path(_fix_filename(f.filename or "unnamed")).name
    data = await f.read()
    if not data:
        return {"filename": filename, "status": "error", "error": "文件为空"}
    if len(data) > MAX_SIZE:
        return {"filename": filename, "status": "error", "error": "文件超过 20MB 限制"}

    # 落盘（时间戳 + 随机片段，避免同一秒同名文件互相覆盖）
    safe_name = f"{db.now():.0f}_{uuid4().hex[:6]}_{filename}"
    stored = db.UPLOAD_DIR / safe_name
    stored.write_bytes(data)

    # 解析 → 识别 → 入库；任一环节失败都清掉落盘文件，不残留孤儿
    try:
        try:
            text = extract_text(stored)
        except UnsupportedFile:
            raise UnsupportedFile(f"暂不支持的文件类型：{filename}")
        if not text.strip():
            stored.unlink(missing_ok=True)
            return {"filename": filename, "status": "error", "error": "未能从文件中提取到文本"}

        # 归属：指定了 project_id 直接用；否则 AI 识别
        created_project = False
        if project_id is not None:
            with db.connect() as conn:
                row = conn.execute(
                    "SELECT id, name, summary FROM projects WHERE id = ?", (project_id,)
                ).fetchone()
            if row is None:
                raise ValueError(f"目标项目不存在（id={project_id}）")
            decision = {"reason": "手动归档到指定项目", "summary": ""}
            target_name = row["name"]
        else:
            # AI 识别归档
            with db.connect() as conn:
                projects = [dict(r) for r in conn.execute("SELECT id, name, summary FROM projects")]
            decision = classify_upload(filename, preview_of(text), projects)
            target_name = None

        with db.connect() as conn:
            if project_id is None:
                project_id = decision.get("match_project_id")
                if project_id is not None:
                    row = conn.execute(
                        "SELECT id FROM projects WHERE id = ?", (project_id,)
                    ).fetchone()
                    if row is None:
                        project_id = None
                if project_id is None:
                    new_name = (decision.get("new_project_name") or "").strip() or filename
                    existing = conn.execute(
                        "SELECT id FROM projects WHERE name = ?", (new_name,)
                    ).fetchone()
                    if existing:
                        project_id = existing["id"]
                    else:
                        cur = conn.execute(
                            "INSERT INTO projects (name, summary, tags, created_at) VALUES (?, ?, ?, ?)",
                            (
                                new_name,
                                decision.get("summary", ""),
                                ",".join(decision.get("tags") or []),
                                db.now(),
                            ),
                        )
                        project_id = cur.lastrowid
                        created_project = True

            cur = conn.execute(
                "INSERT INTO files (project_id, filename, stored_path, size, kind, uploaded_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    filename,
                    str(stored),
                    len(data),
                    Path(filename).suffix.lower().lstrip("."),
                    db.now(),
                ),
            )
            file_id = cur.lastrowid
            chunks = chunk_text(text)
            conn.executemany(
                "INSERT INTO chunks (file_id, project_id, seq, content) VALUES (?, ?, ?, ?)",
                [(file_id, project_id, i, c) for i, c in enumerate(chunks)],
            )
            project = conn.execute(
                "SELECT id, name FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
    except Exception:
        stored.unlink(missing_ok=True)  # 兜底：失败不留孤儿文件
        raise

    return {
        "filename": filename,
        "status": "archived",
        "project_id": project_id,
        "project_name": project["name"],
        "project_created": created_project,
        "reason": decision.get("reason", ""),
        "summary": decision.get("summary", ""),
        "chunks": len(chunks),
    }
