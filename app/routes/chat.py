"""项目内 AI 问答：BM25 检索 → Claude 流式回答（SSE）。"""
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import db
from ..ai_client import answer_question_stream
from ..retrieval import search

router = APIRouter()


class ChatRequest(BaseModel):
    question: str


@router.post("/api/chat/{project_id}")
def chat(project_id: int, req: ChatRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(400, "问题不能为空")

    with db.connect() as conn:
        project = conn.execute(
            "SELECT id, name, summary, intro FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if project is None:
            raise HTTPException(404, "项目不存在")

        history = [
            dict(r)
            for r in conn.execute(
                "SELECT role, content FROM messages WHERE project_id = ? ORDER BY id DESC LIMIT 10",
                (project_id,),
            )
        ][::-1]

        chunk_rows = conn.execute(
            """
            SELECT c.content, f.filename
            FROM chunks c JOIN files f ON f.id = c.file_id
            WHERE c.project_id = ?
            """,
            (project_id,),
        ).fetchall()

        conn.execute(
            "INSERT INTO messages (project_id, role, content, created_at) VALUES (?, 'user', ?, ?)",
            (project_id, question, db.now()),
        )

    contexts = search([dict(r) for r in chunk_rows], question, top_k=8)

    def event_stream():
        parts: list[str] = []
        try:
            for piece in answer_question_stream(
                question=question,
                project_name=project["name"],
                project_summary=project["summary"] or "",
                contexts=contexts,
                history=history,
                project_intro=project["intro"] or "",
            ):
                parts.append(piece)
                yield f"data: {json.dumps({'type': 'text', 'text': piece}, ensure_ascii=False)}\n\n"
            answer = "".join(parts)
            sources = sorted({c["filename"] for c in contexts})
            # 来源写入历史：切换项目重建视图后引用不丢失
            stored = answer + (f"\n\n来源：" + "、".join(sources) if sources else "")
            with db.connect() as conn:
                conn.execute(
                    "INSERT INTO messages (project_id, role, content, created_at)"
                    " VALUES (?, 'assistant', ?, ?)",
                    (project_id, stored, db.now()),
                )
            yield f"data: {json.dumps({'type': 'done', 'sources': sources}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'error': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
