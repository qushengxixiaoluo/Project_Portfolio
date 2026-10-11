"""项目与文件的查询接口。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import db
from ..ai_client import generate_intro

router = APIRouter()


class IntroRequest(BaseModel):
    regenerate: bool = False


class ProjectCreate(BaseModel):
    name: str
    summary: str = ""
    tags: str = ""


@router.post("/api/projects")
def create_project(req: ProjectCreate):
    """手动新建项目（上传文档前先建项目）。"""
    name = req.name.strip()
    if not name:
        raise HTTPException(400, "项目名称不能为空")
    with db.connect() as conn:
        existing = conn.execute(
            "SELECT id FROM projects WHERE name = ?", (name,)
        ).fetchone()
        if existing:
            return {"id": existing["id"], "name": name, "created": False}
        cur = conn.execute(
            "INSERT INTO projects (name, summary, tags, created_at) VALUES (?, ?, ?, ?)",
            (name, req.summary.strip(), req.tags.strip(), db.now()),
        )
        return {"id": cur.lastrowid, "name": name, "created": True}


@router.put("/api/projects/{project_id}")
def update_project(project_id: int, req: ProjectCreate):
    """修改项目名称 / 简介 / 标签。"""
    name = req.name.strip()
    if not name:
        raise HTTPException(400, "项目名称不能为空")
    with db.connect() as conn:
        row = conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "项目不存在")
        dup = conn.execute(
            "SELECT id FROM projects WHERE name = ? AND id != ?", (name, project_id)
        ).fetchone()
        if dup:
            raise HTTPException(400, f"已有同名项目：{name}")
        conn.execute(
            "UPDATE projects SET name = ?, summary = ?, tags = ? WHERE id = ?",
            (name, req.summary.strip(), req.tags.strip(), project_id),
        )
    return {"ok": True, "id": project_id, "name": name}


@router.get("/api/meta")
def meta():
    """存储位置等元信息，供界面显示。"""
    return {"upload_dir": str(db.UPLOAD_DIR), "db_path": str(db.DB_PATH)}


@router.get("/api/projects")
def list_projects():
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT p.*,
                   COUNT(DISTINCT f.id) AS file_count,
                   COUNT(c.id) AS chunk_count
            FROM projects p
            LEFT JOIN files f ON f.project_id = p.id
            LEFT JOIN chunks c ON c.project_id = p.id
            GROUP BY p.id
            ORDER BY p.created_at DESC
            """
        ).fetchall()
        return {"projects": [dict(r) for r in rows]}


@router.get("/api/projects/{project_id}")
def get_project(project_id: int):
    with db.connect() as conn:
        project = conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if project is None:
            raise HTTPException(404, "项目不存在")
        files = conn.execute(
            "SELECT id, filename, size, kind, uploaded_at FROM files"
            " WHERE project_id = ? ORDER BY uploaded_at DESC",
            (project_id,),
        ).fetchall()
        messages = conn.execute(
            "SELECT id, role, content, created_at FROM messages"
            " WHERE project_id = ? ORDER BY id ASC",
            (project_id,),
        ).fetchall()
        return {
            "project": dict(project),
            "files": [dict(r) for r in files],
            "messages": [dict(r) for r in messages],
        }


@router.post("/api/projects/{project_id}/intro")
def make_intro(project_id: int, req: IntroRequest | None = None):
    """生成（或返回已有的）详尽项目介绍。文件数变化时自动视为过期。"""
    with db.connect() as conn:
        project = conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if project is None:
            raise HTTPException(404, "项目不存在")
        files = conn.execute(
            "SELECT filename FROM files WHERE project_id = ?", (project_id,)
        ).fetchall()
        rows = conn.execute(
            "SELECT content FROM chunks WHERE project_id = ? ORDER BY seq", (project_id,)
        ).fetchall()

    force = bool(req and req.regenerate)
    stale = (not project["intro"]) or (project["intro_files"] != len(files))
    if not force and not stale:
        return {"intro": project["intro"], "generated": False}

    if not rows:
        raise HTTPException(400, "项目内还没有可生成介绍的文件")

    text = generate_intro(
        project["name"],
        [f["filename"] for f in files],
        [r["content"] for r in rows],
    )
    with db.connect() as conn:
        conn.execute(
            "UPDATE projects SET intro = ?, intro_files = ?, intro_at = ? WHERE id = ?",
            (text, len(files), db.now(), project_id),
        )
    return {"intro": text, "generated": True}


@router.delete("/api/projects/{project_id}")
def delete_project(project_id: int):
    with db.connect() as conn:
        paths = [
            r["stored_path"]
            for r in conn.execute(
                "SELECT stored_path FROM files WHERE project_id = ?", (project_id,)
            )
        ]
        # messages 表没有外键，需显式清理；chunks/files 由外键级联
        conn.execute("DELETE FROM messages WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM chunks WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM files WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    removed = 0
    from pathlib import Path
    for p in paths:
        try:
            Path(p).unlink(missing_ok=True)
            removed += 1
        except OSError:
            pass
    return {"ok": True, "files_removed": removed}


@router.delete("/api/files/{file_id}")
def delete_file(file_id: int):
    with db.connect() as conn:
        row = conn.execute(
            "SELECT stored_path FROM files WHERE id = ?", (file_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "文件不存在")
        # chunks 由外键级联删除
        conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
        try:
            from pathlib import Path
            Path(row["stored_path"]).unlink(missing_ok=True)
        except OSError:
            pass
    return {"ok": True}
