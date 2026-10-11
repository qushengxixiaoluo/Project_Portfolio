"""Anthropic 客户端封装：模型探测、上传文件归档识别、项目内问答（流式）。"""
import json
import os
import re
from typing import Iterator

import anthropic
from dotenv import load_dotenv

load_dotenv()

# 代理是第三方 Anthropic 兼容服务（小米 MiMo），无 /v1/models 接口，
# 逐个候选模型发一次 tiny 请求来探测可用性
CANDIDATE_MODELS = ["mimo-v2.5-pro", "mimo-v2.5"]

client = anthropic.Anthropic(
    api_key=os.environ.get("ANTHROPIC_API_KEY"),
    base_url=os.environ.get("ANTHROPIC_BASE_URL") or None,
)

MODEL: str | None = None


def detect_model() -> str:
    """探测代理支持的模型，选定一个可用的。"""
    global MODEL
    if MODEL:
        return MODEL
    env_model = os.environ.get("AI_MODEL")
    candidates = [env_model] if env_model else CANDIDATE_MODELS
    last_err: Exception | None = None
    for name in candidates:
        try:
            client.messages.create(
                model=name, max_tokens=8,
                messages=[{"role": "user", "content": "hi"}],
            )
            MODEL = name
            print(f"[ai] 选定模型: {MODEL}")
            return MODEL
        except Exception as exc:
            last_err = exc
            print(f"[ai] 模型 {name} 不可用: {exc}")
    raise RuntimeError(f"代理无可用模型: {last_err}")


def _extract_json(text: str) -> dict:
    """从模型输出中容错提取 JSON 对象。"""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            return json.loads(match.group(0))
        raise


def classify_upload(filename: str, preview: str, projects: list[dict]) -> dict:
    """识别上传文件属于哪个项目（或新建），返回归档决策 JSON。

    返回结构: {match_project_id: int|null, new_project_name: str|null,
               summary: str, tags: list[str], reason: str}
    """
    model = detect_model()
    project_lines = (
        "\n".join(f"- id={p['id']}: {p['name']}（{p['summary']}）" for p in projects)
        if projects
        else "（暂无已有项目）"
    )
    prompt = f"""你是项目归档助手。根据文件内容判断它属于哪个已有项目，或应新建什么项目。

已有项目列表：
{project_lines}

文件名：{filename}
文件内容开头：
\"\"\"{preview[:4000]}\"\"\"

判断原则（重要）：
- 归档单位是"产品/项目"本身：同一产品或系统的全部资料——需求文档(PRD)、设计稿、源码、README、
  测试报告、面试逐字稿、分享稿、学习笔记——都属于同一个项目，应归入同一项目。
- 例：「智慧社区管理平台」的 PRD 与「智慧社区管理平台面试逐字稿」是同一项目，
  应 match 到已有项目（或用同一个 new_project_name），绝不拆成两个项目。
- 只有当文件属于完全不同的产品/系统/主题时，才视为不同项目。

只输出一个 JSON 对象，不要输出其他文字，格式：
{{
  "match_project_id": <已有项目的 id，若不属于任何已有项目则为 null>,
  "new_project_name": <仅当不匹配任何已有项目时，给出简短的中文项目名，否则为 null>,
  "summary": <一两句话概括该文件/所属项目是做什么的>,
  "tags": ["标签1", "标签2"],
  "reason": <一句话说明归档理由>
}}"""
    resp = client.messages.create(
        model=model,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    text = next((b.text for b in resp.content if b.type == "text"), "")
    return _extract_json(text)


def generate_intro(project_name: str, file_names: list[str], texts: list[str]) -> str:
    """根据项目全部文件内容生成一份详尽的项目介绍（Markdown）。"""
    model = detect_model()
    joined = "\n\n".join(t for t in texts if t)[:24000]
    files_line = "、".join(file_names[:80]) or "（暂无）"
    prompt = f"""你是资深技术文档作者。请根据下面的项目文件内容，撰写一份详尽的中文项目介绍。

项目名称：{project_name}
包含文件：{files_line}

文件内容：
{joined}

写作要求：
- 尽量长而充实，1000～1500字；只写文件内容能支撑的细节，不要空话套话。
- 用 Markdown 二级标题（##）分节，按内容取舍这些小节：
  ## 项目概述、## 核心功能与模块、## 技术要点与架构、## 关键参数与数据、## 文件清单说明、## 注意事项
- 某一节文件里没有对应内容就整节省略，不要编造。
- 只输出介绍正文。"""
    with client.messages.stream(
        model=model, max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        msg = stream.get_final_message()
    return next((b.text for b in msg.content if b.type == "text"), "")


def answer_question_stream(
    question: str,
    project_name: str,
    project_summary: str,
    contexts: list[dict],
    history: list[dict],
    project_intro: str = "",
) -> Iterator[str]:
    """项目内问答：带检索上下文与历史，流式产出回答文本。

    contexts: [{filename, content}, ...] 检索到的分块
    history: [{role, content}, ...] 之前的对话
    """
    model = detect_model()
    ctx_blocks = "\n\n".join(
        f"【来源文件：{c['filename']}】\n{c['content']}" for c in contexts
    ) or "（该项目暂无可检索的文件内容）"
    system = f"""你是项目归档库中的 AI 助手，负责回答关于项目「{project_name}」的问题。
项目介绍（由项目文件自动整理，回答时可作为全局背景参考）：
{project_intro or project_summary or '（暂无）'}

以下是根据问题从项目文件中检索到的相关内容，回答时基于它们，并在合适处标注来源文件名：
{ctx_blocks}

要求：仅根据检索内容和对话历史回答；信息不足时明确说明，不要编造。用中文回答。"""

    messages = [m for m in history if m.get("role") in ("user", "assistant")]
    messages = messages[-10:]  # 只保留最近 10 轮，控制上下文
    messages.append({"role": "user", "content": question})

    with client.messages.stream(
        model=model,
        max_tokens=16000,
        system=system,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            yield text
