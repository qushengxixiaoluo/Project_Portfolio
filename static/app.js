/* 档库 ARCHIVE — 前端逻辑 */
const $ = (sel) => document.querySelector(sel);

const state = {
  projects: [],
  currentId: null,      // 当前选中项目
  busyIds: new Set(),   // 正在生成回答的项目 id 集合（每项目独立）
  storageDir: "",       // 服务器上的归档目录（/api/meta 返回）
};
const _introInflight = new Set(); // 正在生成介绍的项目 id（防重复发起）

/* ---------------- API ---------------- */
async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

async function loadProjects() {
  const data = await api("/api/projects");
  state.projects = data.projects;
  renderProjectList();
  renderStat();
}

async function loadMeta() {
  try { state.storageDir = (await api("/api/meta")).upload_dir; } catch (_) {}
}

function renderStat() {
  const files = state.projects.reduce((n, p) => n + p.file_count, 0);
  $("#stat-line").textContent = `${state.projects.length} 个项目 · ${files} 份文件`;
}

function renderProjectList() {
  const list = $("#project-list");
  if (!state.projects.length) {
    list.innerHTML = `<p class="empty-note">尚无归档项目<br>拖入文件，AI 将自动建立第一个项目</p>`;
    return;
  }
  list.innerHTML = state.projects
    .map(
      (p, i) => `
    <button class="project-item ${p.id === state.currentId ? "active" : ""}"
            data-id="${p.id}" style="animation-delay:${i * 40}ms">
      <span class="p-idx">№ ${String(p.id).padStart(3, "0")}</span>
      <span class="p-name">${esc(p.name)}</span>
      <span class="p-meta"><b>${p.file_count}</b> 份文件 · ${p.chunk_count} 个片段</span>
    </button>`
    )
    .join("");
  list.querySelectorAll(".project-item").forEach((el) =>
    el.addEventListener("click", () => selectProject(Number(el.dataset.id)))
  );
}

async function selectProject(id) {
  state.currentId = id;
  renderProjectList();
  const data = await api(`/api/projects/${id}`);
  renderDetail(data);
  renderChatHistory(data.messages, data.project);
  $("#chat-target").textContent = data.project.name;
  $("#chat-input").disabled = false;
  // 该项目有生成任务在跑时保持发送禁用，其他项目不受影响
  $("#chat-send").disabled = state.busyIds.has(id);
  $("#chat-input").placeholder = `就「${data.project.name}」提问…（Enter 发送）`;
  ensureIntro(data.project, data.files.length);
}

/* ---- AI 项目介绍：缺失或文件数变化时自动生成 ---- */
function renderIntro(project) {
  const body = $("#intro-body");
  if (!body) return;
  body.className = "intro-card";
  body.innerHTML = project.intro ? md(project.intro) : "尚未生成介绍。";
}

async function ensureIntro(project, fileCount) {
  const body = $("#intro-body");
  if (!body) return;
  if (fileCount === 0) {
    body.className = "intro-card";
    body.innerHTML = "项目内暂无文件，生成介绍后将显示在这里。";
    return;
  }
  if (project.intro && project.intro_files === fileCount) {
    renderIntro(project);
    return;
  }
  if (_introInflight.has(project.id)) return; // 已有生成在进行，不重复发起（切回来时由它接管渲染）
  body.className = "intro-loading";
  body.textContent = "AI 正在撰写项目介绍";
  _introInflight.add(project.id);
  try {
    const r = await api(`/api/projects/${project.id}/intro`, {
      method: "POST",
      body: JSON.stringify({ regenerate: false }),
    });
    project.intro = r.intro;
    project.intro_files = fileCount;
    if (state.currentId === project.id) renderIntro(project);
  } catch (err) {
    // 只在仍停留在该项目时展示错误；离开过则下次进入重试
    const b = document.getElementById("intro-body");
    if (b && state.currentId === project.id) {
      b.className = "intro-card";
      b.innerHTML = `<span style="color:var(--err)">介绍生成失败：${esc(err.message)}（可点「重新生成」重试）</span>`;
    }
  } finally {
    _introInflight.delete(project.id);
  }
}

async function regenerateIntro(project, fileCount) {
  if (_introInflight.has(project.id)) return;
  const body = $("#intro-body");
  if (!body) return;
  body.className = "intro-loading";
  body.textContent = "AI 正在重新撰写项目介绍";
  _introInflight.add(project.id);
  try {
    const r = await api(`/api/projects/${project.id}/intro`, {
      method: "POST",
      body: JSON.stringify({ regenerate: true }),
    });
    project.intro = r.intro;
    project.intro_files = fileCount;
    if (state.currentId === project.id) renderIntro(project);
  } catch (err) {
    const b = document.getElementById("intro-body");
    if (b && state.currentId === project.id) {
      b.className = "intro-card";
      b.innerHTML = `<span style="color:var(--err)">介绍生成失败：${esc(err.message)}（可点「重新生成」重试）</span>`;
    }
  } finally {
    _introInflight.delete(project.id);
  }
}

/* ---------------- 中栏：卷宗 ---------------- */
function renderDetail(data) {
  const p = data.project;
  const tags = (p.tags || "").split(",").filter(Boolean);
  const files = data.files
    .map(
      (f, i) => `
    <div class="file-row" style="animation-delay:${i * 30}ms">
      <span class="file-badge">${esc(f.kind || "txt")}</span>
      <div class="file-info">
        <div class="file-name" title="${esc(f.filename)}">${esc(f.filename)}</div>
        <div class="file-meta">${fmtSize(f.size)} · ${fmtTime(f.uploaded_at)}</div>
      </div>
      <button class="file-del" data-fid="${f.id}" title="删除文件">✕</button>
    </div>`
    )
    .join("");

  $("#project-detail").innerHTML = `
    <div class="detail-head">
      <span class="d-idx">DOSSIER № ${String(p.id).padStart(3, "0")}</span>
      <h2>${esc(p.name)}</h2>
      <p class="d-summary">${esc(p.summary || "暂无简介")}</p>
      ${tags.length ? `<div class="tag-row">${tags.map((t) => `<span class="tag">${esc(t)}</span>`).join("")}</div>` : ""}
      <div class="detail-actions">
        <button class="btn-ghost" id="btn-edit-project">✏️ 编辑名称简介</button>
        <button class="btn-ghost btn-danger" id="btn-del-project">删除项目</button>
      </div>
      ${state.storageDir ? `<p class="d-storage mono" title="${esc(state.storageDir)}">原始文件存放于 ${esc(state.storageDir)}\\</p>` : ""}
    </div>
    <div class="intro-head">
      <span class="files-label">项目介绍 / INTRODUCTION</span>
      <button class="btn-ghost" id="btn-intro-regen">重新生成</button>
    </div>
    <div id="intro-body" class="intro-loading">AI 正在撰写项目介绍</div>
    <div class="files-label">文件清单 / ${data.files.length} ITEMS</div>
    ${files || `<p class="empty-note">项目内暂无文件</p>`}
  `;

  $("#btn-intro-regen").addEventListener("click", () => regenerateIntro(p, data.files.length));
  $("#btn-edit-project").addEventListener("click", () => openEditProject(p));

  $("#btn-del-project").addEventListener("click", async () => {
    if (!confirm(`确认删除项目「${p.name}」及其全部文件？`)) return;
    try {
      await api(`/api/projects/${p.id}`, { method: "DELETE" });
    } catch (err) {
      alert("删除出错：" + err.message);
    } finally {
      // 无论成功与否都复位界面并刷新索引
      state.currentId = null;
      $("#project-detail").innerHTML = `
        <div class="empty-state"><div class="empty-glyph">❏</div>
        <h2>未选择项目</h2><p>从左侧选择一个项目，或拖入文件开始归档。</p></div>`;
      $("#chat-target").textContent = "未选择项目";
      $("#chat-input").disabled = true;
      $("#chat-send").disabled = true;
      await loadProjects();
    }
  });

  $("#project-detail").querySelectorAll(".file-del").forEach((btn) =>
    btn.addEventListener("click", async () => {
      try {
        await api(`/api/files/${btn.dataset.fid}`, { method: "DELETE" });
      } catch (err) {
        alert("删除出错：" + err.message);
      } finally {
        await loadProjects();
        if (state.currentId) await selectProject(state.currentId);
      }
    })
  );
}

/* ---------------- 上传与归档 ---------------- */
let _pendingFiles = null; // 等待选择目标项目的文件

/* 上传入口：已选中项目 → 直接归入；否则弹目标选择 */
function startUpload(fileList) {
  const files = Array.from(fileList);
  if (!files.length) return;
  // 空文件 / 超 20MB 先本地挡下，不弹任何对话框
  const okFiles = [];
  const invalid = [];
  for (const f of files) {
    if (f.size === 0) invalid.push([f, "文件为空"]);
    else if (f.size > 20 * 1024 * 1024) invalid.push([f, "文件超过 20MB 限制"]);
    else okFiles.push(f);
  }
  if (invalid.length) {
    const tray = getTray();
    for (const [f, err] of invalid) {
      const card = document.createElement("div");
      card.className = "archive-card err";
      card.innerHTML = `
        <div class="ac-name">${esc(f.name)}</div>
        <div class="ac-status">${esc(err)}</div>`;
      tray.appendChild(card);
    }
    tray.scrollTop = tray.scrollHeight;
  }
  if (!okFiles.length) return;
  if (state.currentId) {
    uploadTo(okFiles, { projectId: state.currentId });
  } else if (state.projects.length === 0) {
    openNewProject(okFiles); // 还没有任何项目：先建项目
  } else {
    openTargetModal(okFiles);
  }
}

function getTray() {
  const tray = $("#upload-tray");
  tray.hidden = false;
  // 每次新批次清掉上一批已成功的卡片（错误卡片保留到手动关闭）
  tray.querySelectorAll(".archive-card:not(.err)").forEach((c) => c.remove());
  let title = tray.querySelector(".tray-title");
  if (!title) {
    title = document.createElement("div");
    title.className = "tray-title";
    title.innerHTML = `<span>归档结果 / RESULTS</span><button class="tray-close" title="关闭">✕</button>`;
    title.querySelector(".tray-close").addEventListener("click", () => {
      tray.hidden = true;
      tray.querySelectorAll(".archive-card").forEach((c) => c.remove());
    });
    tray.prepend(title);
  }
  return tray;
}

/* 成功卡片 8 秒后自动消失（信息在卷宗页都有）；有错误则保留 */
function autoDismissTray(cards) {
  const tray = $("#upload-tray");
  const okCards = cards.filter((c) => !c.classList.contains("err"));
  if (!okCards.length) return;
  setTimeout(() => {
    okCards.forEach((c) => c.remove());
    if (!tray.querySelector(".archive-card")) tray.hidden = true;
  }, 8000);
}

/* 新建项目弹层 */
let _editingId = null; // 非空 = 编辑模式

function _resetProjModal(mode) {
  $("#newproj-mask").querySelector("h3").textContent =
    mode === "edit" ? "编辑项目" : "新建项目";
  $("#np-create").textContent = mode === "edit" ? "保存" : "创建";
}

function openNewProject(pendingFiles = null) {
  _pendingFiles = pendingFiles;
  _editingId = null;
  _resetProjModal("create");
  $("#np-name").value = "";
  $("#np-summary").value = "";
  $("#newproj-mask").classList.add("show");
  $("#np-name").focus();
}

function openEditProject(p) {
  _editingId = p.id;
  _pendingFiles = null;
  _resetProjModal("edit");
  $("#np-name").value = p.name || "";
  $("#np-summary").value = p.summary || "";
  $("#newproj-mask").classList.add("show");
  $("#np-name").focus();
  $("#np-name").select();
}

async function createProjectFromModal() {
  const name = $("#np-name").value.trim();
  if (!name) { $("#np-name").focus(); return; }
  const summary = $("#np-summary").value.trim();

  // 编辑模式：改名 / 改简介
  if (_editingId != null) {
    const id = _editingId;
    try {
      await api(`/api/projects/${id}`, {
        method: "PUT",
        body: JSON.stringify({ name, summary }),
      });
      _editingId = null;
      _resetProjModal("create");
      $("#newproj-mask").classList.remove("show");
      await loadProjects();
      await selectProject(id);
    } catch (err) {
      alert("保存失败：" + err.message);
    }
    return;
  }

  try {
    const r = await api("/api/projects", {
      method: "POST",
      body: JSON.stringify({ name, summary }),
    });
    $("#newproj-mask").classList.remove("show");
    await loadProjects();
    await selectProject(r.id);
    if (_pendingFiles) {
      const files = _pendingFiles;
      _pendingFiles = null;
      uploadTo(files, { projectId: r.id });
    }
  } catch (err) {
    alert("创建失败：" + err.message);
  }
}

/* 上传目标选择弹层 */
function openTargetModal(files) {
  _pendingFiles = files;
  const list = $("#target-list");
  list.innerHTML = state.projects.map((p, i) => `
    <label class="target-opt">
      <input type="radio" name="target-mode" value="project" data-id="${p.id}" ${i === 0 ? "checked" : ""}>
      <span>${esc(p.name)}</span>
    </label>`).join("");
  $("#target-newname").value = "";
  $("#target-ai").checked = false;
  $("#target-mask").classList.add("show");
}

function resolveTargetModal() {
  const newname = $("#target-newname").value.trim();
  const ai = $("#target-ai").checked;
  const checked = document.querySelector('#target-list input:checked');
  $("#target-mask").classList.remove("show");
  const files = _pendingFiles;
  _pendingFiles = null;
  if (!files) return;
  if (ai) uploadTo(files, { ai: true });
  else if (newname) uploadTo(files, { newName: newname });
  else if (checked) uploadTo(files, { projectId: Number(checked.dataset.id) });
}

async function uploadTo(files, target) {
  // 新建项目（指定名称）
  if (target.newName) {
    try {
      const r = await api("/api/projects", {
        method: "POST",
        body: JSON.stringify({ name: target.newName }),
      });
      target = { projectId: r.id, created: r.created };
    } catch (err) {
      alert("新建项目失败：" + err.message);
      return;
    }
  }

  const tray = getTray();

  const scanning = target.ai ? "AI 正在识别所属项目" : "正在解析并归档…";
  const cards = files.map((f) => {
    const card = document.createElement("div");
    card.className = "archive-card";
    card.innerHTML = `
      <div class="ac-name">${esc(f.name)}</div>
      <div class="ac-status"><span class="scanning">${scanning}</span></div>`;
    tray.appendChild(card);
    return card;
  });
  tray.scrollTop = tray.scrollHeight;

  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  if (!target.ai && target.projectId) form.append("project_id", String(target.projectId));

  try {
    const res = await fetch("/api/upload", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);

    data.results.forEach((r, i) => {
      const card = cards[i];
      if (!card) return;
      if (r.status === "archived") {
        card.classList.remove("err");
        card.innerHTML = `
          <div class="ac-name">${esc(r.filename)}
            ${r.project_created ? `<span class="seal-new">新建</span>` : ""}</div>
          <div class="ac-status">归入项目 <b>${esc(r.project_name)}</b> · ${r.chunks} 个片段</div>
          <div class="ac-reason">${esc(r.reason || "")}</div>`;
      } else {
        card.classList.add("err");
        card.innerHTML = `
          <div class="ac-name">${esc(r.filename)}</div>
          <div class="ac-status">${esc(r.error || "失败")}</div>`;
      }
    });

    await loadProjects();
    const first = data.results.find((r) => r.status === "archived");
    if (first) await selectProject(first.project_id);
  } catch (err) {
    cards.forEach((card) => {
      card.classList.add("err");
      card.querySelector(".ac-status").innerHTML = `上传失败：${esc(err.message)}`;
    });
  }
  autoDismissTray(cards);
}

/* ---------------- 聊天 ---------------- */
function addMsg(role, text = "") {
  const log = $("#chat-log");
  const empty = log.querySelector(".chat-empty");
  if (empty) empty.remove();
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.innerHTML = `
    <div class="m-role">${role === "user" ? "你 / YOU" : "AI 档案员 / ARCHIVIST"}</div>
    <div class="m-body"></div>`;
  const body = el.querySelector(".m-body");
  if (role === "assistant") body.innerHTML = md(text);
  else body.textContent = text;
  log.appendChild(el);
  log.scrollTop = log.scrollHeight;
  return el;
}

/* 轻量 Markdown 渲染（先转义再转换，防注入） */
function md(src) {
  let s = esc(src);
  const blocks = [];
  s = s.replace(/```[\w-]*\n?([\s\S]*?)```/g, (_, code) => {
    blocks.push(`<pre>${code.trim()}</pre>`);
    return `\u0000${blocks.length - 1}\u0000`;
  });
  s = s.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  s = s.replace(/\*\*([\s\S]+?)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/^#{1,4}\s+(.*)$/gm, "<h4>$1</h4>");
  // 列表行分组
  s = s.replace(/((?:^[-*•]\s+.*$\n?)+)/gm, (m) => {
    const items = m.trim().split("\n").map((l) => `<li>${l.replace(/^[-*•]\s+/, "")}</li>`).join("");
    return `<ul>${items}</ul>`;
  });
  s = s.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>"); // 行内斜体
  s = s.replace(/\u0000(\d+)\u0000/g, (_, i) => blocks[i]);
  s = s.replace(/\n/g, "<br>")
    .replace(/<br>(<ul>|<pre>|<h4>)/g, "$1")
    .replace(/(<\/ul>|<\/pre>|<\/h4>)<br>/g, "$1");
  return s;
}

function renderChatHistory(messages, project) {
  const log = $("#chat-log");
  log.innerHTML = `
    <div class="chat-empty">
      <p class="chat-empty-title">AI 档案员</p>
      <p>关于「${esc(project.name)}」，尽管问。<br>回答基于检索到的项目文件，并标注来源。</p>
    </div>`;
  messages.forEach((m) => addMsg(m.role, m.content));
}

async function sendQuestion(question) {
  if (!state.currentId) return;
  const pid = state.currentId;
  if (state.busyIds.has(pid)) return;
  state.busyIds.add(pid);
  $("#chat-send").disabled = true;

  addMsg("user", question);
  const assistantEl = addMsg("assistant", "");
  const body = assistantEl.querySelector(".m-body");
  body.classList.add("cursor-blink");

  const log = $("#chat-log");
  // 视图还挂在页面上且仍是该项目时才更新 DOM；切走后生成在后台继续
  const live = () => document.body.contains(body) && state.currentId === pid;
  let answer = "";
  try {
    const res = await fetch(`/api/chat/${pid}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!res.ok || !res.body) throw new Error(`请求失败 (${res.status})`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop();
      for (const evt of events) {
        const line = evt.trim();
        if (!line.startsWith("data:")) continue;
        let payload;
        try { payload = JSON.parse(line.slice(5).trim()); } catch { continue; }
        if (payload.type === "text") {
          answer += payload.text;
          if (live()) {
            body.innerHTML = md(answer);
            log.scrollTop = log.scrollHeight;
          }
        } else if (payload.type === "done") {
          if (live()) {
            body.classList.remove("cursor-blink");
            if (payload.sources?.length) {
              const src = document.createElement("div");
              src.className = "m-sources";
              src.innerHTML = payload.sources
                .map((s) => `<span class="src-chip">📄 ${esc(s)}</span>`)
                .join("");
              assistantEl.appendChild(src);
            }
          } else if (state.currentId === pid) {
            // 用户切走又切回：原视图已销毁，重建聊天区接上完成的回答
            // （服务端在 done 前已保存，历史里有完整内容）
            await selectProject(pid);
          }
        } else if (payload.type === "error") {
          throw new Error(payload.error);
        }
      }
    }
    if (live()) {
      body.classList.remove("cursor-blink");
      if (!answer) body.textContent = "（未收到回答）";
    }
  } catch (err) {
    if (document.body.contains(body)) {
      body.classList.remove("cursor-blink");
      if (answer) {
        // 中断但已有部分内容：保留已生成的回答，追加错误提示，不覆盖
        const note = document.createElement("div");
        note.className = "msg-error";
        note.style.marginTop = "6px";
        note.textContent = `⚠ 回答中断：${err.message}（已保留部分内容）`;
        assistantEl.appendChild(note);
      } else {
        assistantEl.classList.add("msg-error");
        body.textContent = `出错了：${err.message}`;
      }
    }
  } finally {
    state.busyIds.delete(pid);
    if (state.currentId === pid) $("#chat-send").disabled = false;
    if (document.body.contains(log)) log.scrollTop = log.scrollHeight;
  }
}

/* ---------------- 事件绑定 ---------------- */
$("#btn-upload-top").addEventListener("click", () => $("#file-input").click());
$("#dropzone").addEventListener("click", () => $("#file-input").click());

/* 新建项目 / 上传目标弹层 */
$("#btn-new-project").addEventListener("click", () => openNewProject(null));
$("#np-cancel").addEventListener("click", () => {
  _pendingFiles = null;
  _editingId = null;
  _resetProjModal("create");
  $("#newproj-mask").classList.remove("show");
});
$("#np-create").addEventListener("click", createProjectFromModal);
$("#np-name").addEventListener("keydown", (e) => {
  if (e.key === "Enter") createProjectFromModal();
});
$("#target-cancel").addEventListener("click", () => {
  _pendingFiles = null;
  $("#target-mask").classList.remove("show");
});
$("#target-ok").addEventListener("click", resolveTargetModal);
$("#newproj-mask").addEventListener("click", (e) => {
  if (e.target === $("#newproj-mask")) {
    _pendingFiles = null; _editingId = null; _resetProjModal("create");
    $("#newproj-mask").classList.remove("show");
  }
});
$("#target-mask").addEventListener("click", (e) => {
  if (e.target === $("#target-mask")) { _pendingFiles = null; $("#target-mask").classList.remove("show"); }
});
$("#file-input").addEventListener("change", (e) => {
  startUpload(e.target.files);
  e.target.value = "";
});

["dragover", "dragenter"].forEach((ev) =>
  document.addEventListener(ev, (e) => {
    e.preventDefault();
    $("#dropzone").classList.add("over");
  })
);
["dragleave", "drop"].forEach((ev) =>
  document.addEventListener(ev, (e) => {
    e.preventDefault();
    if (ev === "drop" || e.target === document.documentElement) {
      $("#dropzone").classList.remove("over");
    }
  })
);
document.addEventListener("drop", (e) => {
  e.preventDefault();
  if (e.dataTransfer?.files?.length) startUpload(e.dataTransfer.files);
});

$("#chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const input = $("#chat-input");
  const q = input.value.trim();
  if (!q) return;
  input.value = "";
  sendQuestion(q);
});
$("#chat-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    $("#chat-form").requestSubmit();
  }
});

/* ---------------- 工具 ---------------- */
function esc(s) {
  return String(s ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}
function fmtSize(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
function fmtTime(ts) {
  return new Date(ts * 1000).toLocaleString("zh-CN", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

loadMeta()
  .then(loadProjects)
  .catch((err) => {
    $("#project-list").innerHTML = `<p class="empty-note">加载失败：${esc(err.message)}</p>`;
  });
