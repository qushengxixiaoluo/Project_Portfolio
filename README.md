# 档库 ARCHIVE — 项目归档 + AI 问答

上传文件，AI 自动识别它属于哪个项目并归档；在每个项目内向 AI 提问，AI 检索整个项目的文件内容来回答，并标注来源。

## 两个版本

| | **单文件版（推荐个人使用）** | **后端版** |
|---|---|---|
| 入口 | `standalone/index.html`（双击打开） | `uvicorn main:app` |
| 依赖 | 无后端，浏览器直连 AI 接口 | FastAPI 服务 |
| 存储 | 浏览器 IndexedDB（降级 localStorage），可导出/导入 JSON | SQLite 落盘 |
| PDF/Word | 按需从 CDN 加载 pdf.js / mammoth | pypdf / python-docx |
| 适用 | 本机个人使用、静态托管分享 | 有 PDF/Word 重度需求、团队共用 |

## 功能

- **手动建项目归档（推荐流程）**：左栏「＋新建项目」→ 在项目内上传文档（未选中项目时会弹窗
  选择/新建，或勾选"让 AI 自动识别归属"）；同一产品的 PRD、面试稿、源码等全部归同一项目
- **拖拽上传（支持多选）**：支持 PDF / Word / Markdown / 代码 / 文本等格式（≤20MB），
  非法文件本地预校验直接提示，不浪费 AI 调用
- **AI 自动归档（可选）**：按"产品/系统"识别归属——同一产品的全部资料归同一项目，给出归档理由
- **存储位置可见**：
  - 后端版：**全程 0 询问**——自动平铺写入 `data\uploads\`（文件名含时间戳前缀），
    项目归属看详情页显示的完整路径
  - 单文件版：浏览器安全硬限制决定了"选文件夹的系统对话框必须由你亲手点一次"，但**只有首次**：
    选了 → 终身静默写 `<文件夹>/<项目名>/`，完整索引（项目/文件/分块/聊天/介绍）写 `<文件夹>/档库索引.json`，
    刷新自动恢复；**取消一次 → 永久记住、之后永不再弹**（原件只保留解析文本，卡片如实标注），
    随时可在 设置→归档文件夹 手动连接；浏览器重启后权限偶发降级 → 上传瞬间地址栏点一次"允许"即续
- **AI 项目介绍**：根据项目全部文件自动生成 1000+ 字的详尽介绍（概述/功能/架构/参数/注意事项分节），
  展示在项目卷宗中；文件变动自动更新，可手动「重新生成」；问答时作为全局背景
- **项目内 AI 问答**：BM25 中文检索相关片段 → 流式生成回答 → 标注来源文件
- **异常兜底**：上传失败不留孤儿文件；流式回答中断保留部分内容；AI 不可用时界面横幅提示；
  设置内可「测试连接」；删除按钮红色且同步清理原件（磁盘/文件夹）

## 技术栈

- 后端：FastAPI + SQLite，`anthropic` SDK（Anthropic 兼容代理 + 小米 MiMo 模型）
- 检索：`rank_bm25` + `jieba`（检索层独立成模块，可替换为向量检索）
- 前端：原生 HTML/CSS/JS，三栏档案馆风格界面，SSE 流式聊天

## 启动

**Windows 推荐：双击 `启动归档.bat`** —— 自动启动服务并打开浏览器，归档全程 0 询问，
原件自动写入 `data\uploads\`（资源管理器可见；关掉服务窗口即停服）。

手动方式（备选）：

```bash
pip install -r requirements.txt
python -m uvicorn main:app --port 8000
```

浏览器打开 http://127.0.0.1:8000

## 配置（.env）

```ini
ANTHROPIC_API_KEY=<你的 token>
ANTHROPIC_BASE_URL=<Anthropic 兼容代理地址>
AI_MODEL=<可选，指定模型，默认自动探测 mimo-v2.5-pro / mimo-v2.5>
```

## 目录结构

```
main.py               # FastAPI 入口
app/
  db.py               # SQLite 表结构与连接
  ai_client.py        # AI 客户端：模型探测、归档识别、流式问答
  parser.py           # 文本提取（pdf/docx/代码/文本）与分块
  retrieval.py        # BM25 检索
  routes/             # upload / projects / chat 接口
static/               # 前端页面
sample_files/         # 演示用样例文件
data/                 # 运行时数据库与上传文件（自动创建）
```

## 演示

```bash
curl -X POST http://127.0.0.1:8000/api/upload \
  -F "files=@sample_files/thermostat_README.md" \
  -F "files=@sample_files/thermostat_pid.py" \
  -F "files=@sample_files/printer_stepper.md"
```
