const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("messageInput");
const sendStopBtn = document.getElementById("sendStopButton");
const newConversationBtn = document.getElementById("newConversationButton");
const conversationListEl = document.getElementById("conversationList");
const conversationEmptyEl = document.getElementById("conversationEmpty");
const resetMemoryBtn = document.getElementById("resetMemoryBtn");
const batchModeBtn = document.getElementById("batchModeBtn");
const batchActionBar = document.getElementById("batchActionBar");
const batchCountEl = document.getElementById("batchCount");
const batchSelectAllBtn = document.getElementById("batchSelectAllBtn");
const batchDeleteBtn = document.getElementById("batchDeleteBtn");
const batchCancelBtn = document.getElementById("batchCancelBtn");
const searchInputEl = document.getElementById("searchInput");
const menuToggleBtn = document.getElementById("menuToggleBtn");
const sidebarEl = document.getElementById("sidebar");
const sidebarBackdrop = document.getElementById("sidebarBackdrop");
const toastContainer = document.getElementById("toastContainer");

const CHAT_STORE_KEY = "agent_chat_store_v2";
const LEGACY_HISTORY_KEY = "agent_chat_history_v1";
const MAX_CONVERSATIONS = 50;
const MAX_MESSAGES_PER_CONVERSATION = 200;

const state = {
  generating: false,
  abortController: null,
  currentAssistant: null,
  batchMode: false,
  batchSelected: new Set(),
  store: {
    activeConversationId: "",
    conversations: [],
  },
};

if (window.marked) {
  window.marked.setOptions({ gfm: true, breaks: true });
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderMarkdown(rawText) {
  const text = String(rawText || "");
  if (window.marked && window.DOMPurify) {
    return window.DOMPurify.sanitize(window.marked.parse(text));
  }
  return escapeHtml(text).replaceAll("\n", "<br>");
}

function makeConversationId() {
  return `conv_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}
function nowTs() { return Date.now(); }

function formatTime(ts) {
  const d = new Date(ts || Date.now());
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function normalizeAssistantMessage(item) {
  const segments = Array.isArray(item.segments) ? item.segments : [];
  const safeSegments = [];
  for (const seg of segments) {
    if (!seg || typeof seg !== "object") continue;
    if (seg.type === "text") {
      safeSegments.push({ type: "text", content: String(seg.content || "") });
    } else if (seg.type === "tool_call") {
      safeSegments.push({
        type: "tool_call",
        name: String(seg.name || "tool"),
        args: seg.args && typeof seg.args === "object" ? seg.args : {},
        result: String(seg.result || ""),
      });
    }
  }
  const msg = { role: "assistant", segments: safeSegments };
  if (item.token_stats && typeof item.token_stats === "object") {
    msg.token_stats = {
      input_tokens: Number(item.token_stats.input_tokens || 0),
      output_tokens: Number(item.token_stats.output_tokens || 0),
      llm_calls: Number(item.token_stats.llm_calls || 0),
    };
  }
  return msg;
}

function normalizeMessages(rawMessages) {
  if (!Array.isArray(rawMessages)) return [];
  const normalized = [];
  for (const item of rawMessages) {
    if (!item || typeof item !== "object") continue;
    if (item.role === "user") { normalized.push({ role: "user", content: String(item.content || "") }); continue; }
    if (item.role === "assistant") normalized.push(normalizeAssistantMessage(item));
  }
  if (normalized.length > MAX_MESSAGES_PER_CONVERSATION) return normalized.slice(-MAX_MESSAGES_PER_CONVERSATION);
  return normalized;
}

function buildConversationTitle(conversation) {
  const firstUser = (conversation.messages || []).find((m) => m.role === "user" && String(m.content || "").trim());
  if (!firstUser) return "新对话";
  const text = String(firstUser.content || "").replace(/\s+/g, " ").trim();
  if (!text) return "新对话";
  return text.length > 24 ? `${text.slice(0, 24)}...` : text;
}

function createEmptyConversation() {
  const ts = nowTs();
  return { id: makeConversationId(), title: "新对话", createdAt: ts, updatedAt: ts, messages: [] };
}

function normalizeConversation(raw) {
  const ts = nowTs();
  const conv = {
    id: typeof raw.id === "string" && raw.id.trim() ? raw.id : makeConversationId(),
    title: typeof raw.title === "string" && raw.title.trim() ? raw.title : "新对话",
    createdAt: Number(raw.createdAt || ts),
    updatedAt: Number(raw.updatedAt || ts),
    messages: normalizeMessages(raw.messages),
  };
  if (!conv.title || conv.title === "新对话") conv.title = buildConversationTitle(conv);
  return conv;
}

function migrateLegacyHistoryIfNeeded() {
  try {
    var legacyRaw = window.localStorage.getItem(LEGACY_HISTORY_KEY);
    if (!legacyRaw) return null;
    window.localStorage.removeItem(LEGACY_HISTORY_KEY);
    var legacyMessages = normalizeMessages(JSON.parse(legacyRaw));
    if (!legacyMessages.length) return null;
    return legacyMessages;
  } catch (_) { return null; }
}

var _chatApi = {
  _fetch: function(method, url, body) {
    var opts = { method: method, headers: { "Content-Type": "application/json" } };
    if (body !== undefined && body !== null) opts.body = JSON.stringify(body);
    return fetch(url, opts).then(function(r) { return r.json(); });
  },
  listConversations: function() { return this._fetch("GET", "/api/chat/conversations"); },
  getConversation: function(id) { return this._fetch("GET", "/api/chat/conversations/" + id); },
  createConversation: function(title) { return this._fetch("POST", "/api/chat/conversations", { title: title || "新对话" }); },
  activateConversation: function(id) { return this._fetch("POST", "/api/chat/conversations/" + id + "/activate"); },
  deleteConversation: function(id) { return this._fetch("DELETE", "/api/chat/conversations/" + id); },
  batchDeleteConversations: function(ids) { return this._fetch("POST", "/api/chat/conversations/batch-delete", { ids: ids }); },
  appendMessage: function(convId, role, content) {
    var body = { role: role };
    if (content !== undefined) body.content = content;
    return this._fetch("POST", "/api/chat/conversations/" + convId + "/messages", body);
  },
  updateMessage: function(convId, msgId, action, data) {
    data.action = action;
    return this._fetch("PATCH", "/api/chat/conversations/" + convId + "/messages/" + msgId, data);
  },
  touchConversation: function(id) { return this._fetch("POST", "/api/chat/conversations/" + id + "/touch"); },
  updateTitle: function(id, title) { return this._fetch("POST", "/api/chat/conversations/" + id + "/title", { title: title }); },
};

async function loadStoreFromAPI() {
  try {
    var res = await _chatApi.listConversations();
    state.store.conversations = Array.isArray(res.conversations) ? res.conversations : [];
    for (var i = 0; i < state.store.conversations.length; i++) {
      if (!state.store.conversations[i].messages) state.store.conversations[i].messages = [];
    }
    state.store.activeConversationId = res.activeId || "";
    if (!state.store.conversations.length) {
      var newConv = await _chatApi.createConversation();
      if (newConv.ok && newConv.conversation) {
        state.store.conversations.push(newConv.conversation);
        state.store.activeConversationId = newConv.conversation.id;
      }
    } else if (!state.store.activeConversationId || !state.store.conversations.some(function(c) { return c.id === state.store.activeConversationId; })) {
      state.store.activeConversationId = state.store.conversations[0].id;
    }
    console.log("[loadFromAPI] 完成", { convs: state.store.conversations.length, activeId: state.store.activeConversationId });
  } catch (e) {
    console.error("[loadFromAPI] 异常", e);
    if (!state.store.conversations.length) {
      state.store.conversations.push({ id: makeConversationId(), title: "新对话", createdAt: nowTs(), updatedAt: nowTs(), messages: [] });
      state.store.activeConversationId = state.store.conversations[0].id;
    }
  }
}

async function loadActiveConversationMessages() {
  var convId = state.store.activeConversationId;
  if (!convId) return;
  try {
    var res = await _chatApi.getConversation(convId);
    if (res.ok && res.messages) {
      var conv = state.store.conversations.find(function(c) { return c.id === convId; });
      if (conv) conv.messages = res.messages;
      console.log("[loadActiveMsgs] 从DB加载", { msgs: res.messages.length, convId: convId });
    }
  } catch (e) {
    console.error("[loadActiveMsgs] 异常", e);
  }
}

function saveStore() {}

function _dbId(msgObj) { return msgObj.dbId || null; }

function dbCreateConversation(title) {
  return _chatApi.createConversation(title).then(function(res) {
    var conv = (res.ok && res.conversation) ? res.conversation : createEmptyConversation();
    if (!conv.messages) conv.messages = [];
    return conv;
  }).catch(function() { return createEmptyConversation(); });
}

function dbAppendUserMessage(convId, content) {
  return _chatApi.appendMessage(convId, "user", content).then(function(res) { return res.ok ? res.message : null; }).catch(function() { return null; });
}

function dbCreateAssistantMessage(convId) {
  return _chatApi.appendMessage(convId, "assistant").then(function(res) { return res.ok ? res.message : null; }).catch(function() { return null; });
}

function dbAppendText(convId, msgDbId, delta) { _chatApi.updateMessage(convId, msgDbId, "append_text", { content: delta }).catch(function(){}); }
function dbAppendReasoning(convId, msgDbId, delta) { _chatApi.updateMessage(convId, msgDbId, "append_reasoning", { content: delta }).catch(function(){}); }
function dbAddToolCall(convId, msgDbId, name, args) { _chatApi.updateMessage(convId, msgDbId, "add_tool_call", { name: name, args: args }).catch(function(){}); }
function dbSetToolResult(convId, msgDbId, result) { _chatApi.updateMessage(convId, msgDbId, "set_tool_result", { result: result }).catch(function(){}); }
function dbSetTokenStats(convId, msgDbId, stats) { _chatApi.updateMessage(convId, msgDbId, "set_token_stats", { stats: stats }).catch(function(){}); }
function dbTouch(convId) { _chatApi.touchConversation(convId).catch(function(){}); }

function getActiveConversation() {
  let conv = state.store.conversations.find((c) => c.id === state.store.activeConversationId);
  if (!conv) {
    conv = createEmptyConversation();
    state.store.conversations.unshift(conv);
    state.store.activeConversationId = conv.id;
  }
  return conv;
}

function touchConversation(conversation) {
  conversation.updatedAt = nowTs(); conversation.title = buildConversationTitle(conversation);
  dbTouch(conversation.id);
}

function flattenAssistantMessageToText(msg) {
  if (!msg || typeof msg !== "object") return "";
  const parts = [];
  for (const seg of Array.isArray(msg.segments) ? msg.segments : []) {
    if (!seg || typeof seg !== "object") continue;
    if (seg.type === "text") { const t = String(seg.content || "").trim(); if (t) parts.push(t); }
    else if (seg.type === "tool_call") { const r = String(seg.result || "").trim(); if (r) parts.push(`[工具 ${String(seg.name || "tool")} 返回]\n${r}`); }
  }
  return parts.join("\n\n").trim();
}

/* ========== Toast ========== */
let toastCounter = 0;
function showToast(message, type = "info") {
  toastCounter++;
  const icons = { success: "\u2713", error: "\u2717", info: "\u2139" };
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.innerHTML = `<span class="toast-icon">${icons[type] || ""}</span><span class="toast-message">${escapeHtml(message)}</span>`;
  el.dataset.tid = toastCounter;
  toastContainer.appendChild(el);

  setTimeout(() => { el.classList.add("hiding"); setTimeout(() => el.remove(), 220); }, 3000);
  if (toastContainer.children.length > 3) { const first = toastContainer.firstChild; first.classList.add("hiding"); setTimeout(() => first.remove(), 220); }
}


/* ========== Modal ========== */
function showModal(title, desc, onConfirm) {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.innerHTML = `
    <div class="modal">
      <div class="modal-title">${escapeHtml(title)}</div>
      <div class="modal-desc">${desc}</div>
      <div class="modal-actions">
        <button class="btn-modal-cancel">取消</button>
        <button class="btn-modal-danger">确认删除</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);

  const close = () => { overlay.remove(); document.removeEventListener("keydown", escHandler); };
  const escHandler = (e) => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", escHandler);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
  overlay.querySelector(".btn-modal-cancel").addEventListener("click", close);
  overlay.querySelector(".btn-modal-danger").addEventListener("click", () => { close(); onConfirm?.(); });
}


/* ========== Sidebar Toggle ========== */
menuToggleBtn.addEventListener("click", () => toggleSidebar(true));
sidebarBackdrop.addEventListener("click", () => toggleSidebar(false));

function toggleSidebar(open) {
  sidebarEl.classList.toggle("open", open);
  sidebarBackdrop.classList.toggle("show", open);
}


/* ========== Generating State ========== */
function setGenerating(flag) {
  state.generating = flag;
  sendStopBtn.innerHTML = flag
    ? '停止 <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><rect x="6" y="6" width="12" height="12"/></svg>'
    : '发送 <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>';
  sendStopBtn.classList.toggle("danger", flag);

  inputEl.disabled = flag;
  if (!flag) inputEl.focus();
}

function scrollToBottom() { messagesEl.scrollTop = messagesEl.scrollHeight; }


/* ========== Auto-resize textarea ========== */
inputEl.addEventListener("input", () => {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 160) + "px";
});


/* ========== Conversation List Rendering ========== */
function renderConversationList(filter = "") {
  conversationListEl.innerHTML = "";
  const q = filter.toLowerCase().trim();
  let sorted = [...state.store.conversations].sort((a, b) => b.updatedAt - a.updatedAt);
  if (q) sorted = sorted.filter((c) => c.title.toLowerCase().includes(q));

  if (!sorted.length) {
    conversationEmptyEl.style.display = "block";
    conversationEmptyEl.textContent = q ? "没有匹配的对话" : "暂无历史对话";
    return;
  }

  conversationEmptyEl.style.display = "none";

  if (state.batchMode) {
    conversationListEl.classList.add("batch-mode");
    sidebarEl.classList.add("batch-mode-active");
  } else {
    conversationListEl.classList.remove("batch-mode");
    sidebarEl.classList.remove("batch-mode-active");
  }

  for (const conv of sorted) {
    const li = document.createElement("li");
    const item = document.createElement("div");
    item.className = "conversation-item" + (state.batchMode ? " batch-mode" : "");
    if (conv.id === state.store.activeConversationId) item.classList.add("active");
    if (state.batchMode && state.batchSelected.has(conv.id)) { item.classList.add("batch-selected"); }

    const main = document.createElement("div");
    main.className = "conversation-main";

    const title = document.createElement("div");
    title.className = "conversation-title";
    title.textContent = conv.title || "新对话";

    const meta = document.createElement("div");
    meta.className = "conversation-meta";
    meta.textContent = `${(conv.messages && conv.messages.length) || 0} 条消息 · ${formatTime(conv.updatedAt)}`;

    main.appendChild(title); main.appendChild(meta);
    main.addEventListener("click", () => {
      if (state.batchMode) { toggleBatchSelect(conv.id); }
      else { switchConversation(conv.id); }
    });

    if (state.batchMode) {
      const check = document.createElement("div");
      check.className = "conversation-batch-check" + (state.batchSelected.has(conv.id) ? " checked" : "");
      check.addEventListener("click", (e) => { e.stopPropagation(); toggleBatchSelect(conv.id); });
      item.appendChild(check);
    }

    const actions = document.createElement("details");
    actions.className = "conversation-actions";
    const trigger = document.createElement("summary");
    trigger.textContent = "\u22EF";

    const menu = document.createElement("div");
    menu.className = "conversation-menu";
    const deleteBtn = document.createElement("button");
    deleteBtn.type = "button"; deleteBtn.textContent = "删除对话";
    deleteBtn.addEventListener("pointerdown", (e) => e.stopPropagation());
    deleteBtn.addEventListener("click", async (e) => {
      e.preventDefault(); e.stopPropagation(); actions.open = false;
      showModal(
        "删除对话",
        `确定要删除对话「${conv.title}」吗？此操作不可撤销。`,
        () => deleteConversation(conv.id)
      );
    });

    menu.appendChild(deleteBtn); actions.appendChild(trigger); actions.appendChild(menu);
    actions.addEventListener("toggle", () => {
      if (!actions.open) return;
      for (const other of document.querySelectorAll(".conversation-actions[open]")) { if (other !== actions) other.open = false; }
      const rect = trigger.getBoundingClientRect();
      menu.style.right = (window.innerWidth - rect.right + 4) + "px";
      menu.style.top = (rect.bottom + 4) + "px";
    });
    actions.addEventListener("click", (e) => e.stopPropagation());

    item.appendChild(main); item.appendChild(actions);
    li.appendChild(item); conversationListEl.appendChild(li);
  }
}

searchInputEl.addEventListener("input", () => renderConversationList(searchInputEl.value));


/* ========== Welcome Screen ========== */
function renderWelcome() {
  const node = document.createElement("div");
  node.className = "messages-empty";
  node.innerHTML = `
    <div class="welcome-card">
      <div class="welcome-icon">A</div>
      <h2>有什么可以帮你的？</h2>
      <p>我是你的本地 AI Agent 助手，支持多轮对话、工具调用和知识库检索。可以直接提问，也可以前往知识库页面上传文档。</p>
      <div class="welcome-suggestions">
        <button class="suggestion-chip" data-q="刑法中关于正当防卫的规定是什么？">正当防卫的规定</button>
        <button class="suggestion-chip" data-q="什么是缓刑？适用条件有哪些？">缓刑的适用条件</button>
        <button class="suggestion-chip" data-q="自首和坦白有什么区别？">自首与坦白的区别</button>
      </div>
    </div>`;
  messagesEl.appendChild(node);

  node.querySelectorAll(".suggestion-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const q = chip.dataset.q || chip.textContent.trim();
      inputEl.value = q; sendMessage();
    });
  });
}


/* ========== Message DOM ========== */
function renderUserMessageDom(text) {
  const node = document.createElement("div");
  node.className = "message role-user";
  node.innerHTML = `<div class="bubble">${escapeHtml(text)}</div>`;
  messagesEl.appendChild(node);
}

function createToolDetails(name, args, resultText) {
  const details = document.createElement("details");
  details.className = "tool-block"; details.open = false;

  const summary = document.createElement("summary");
  summary.innerHTML = `<span class="tool-icon">\u2699</span>${name}<span class="tool-chevron">\u25BC</span>`;

  const body = document.createElement("div");
  body.className = "tool-body";
  const argsBlock = document.createElement("pre");
  argsBlock.textContent = JSON.stringify(args || {}, null, 2);
  var resultBlock;
  if (name === "rag_query") {
    resultBlock = document.createElement("div");
    resultBlock.className = "rag-result-container";
    resultBlock.textContent = String(resultText || "等待工具返回...");
  } else {
    resultBlock = document.createElement("pre");
    resultBlock.textContent = String(resultText || "等待工具返回...");
  }

  body.appendChild(argsBlock); body.appendChild(resultBlock);
  details.appendChild(summary); details.appendChild(body);
  return { details, resultBlock };
}

function createAssistantMessageEntry() {
  return { role: "assistant", segments: [] };
}

function createAssistantMessageDom(entry) {
  const node = document.createElement("div");
  node.className = "message role-assistant";

  const header = document.createElement("div");
  header.className = "msg-header";
  header.innerHTML = `<div class="msg-avatar assistant">A</div><span class="msg-sender">Assistant</span>`;

  const bodyWrap = document.createElement("div");
  bodyWrap.className = "assistant-flow";
  const statsWrap = document.createElement("div");

  node.appendChild(header); node.appendChild(bodyWrap); node.appendChild(statsWrap);
  messagesEl.appendChild(node);
  return {
    node, bodyWrap, statsWrap, entry,
    toolCalls: [], hasOutput: false,
    rounds: [], currentRound: null, roundIndex: 0,
  };
}

function startNewRound(msgObj) {
  msgObj.roundIndex++;
  const roundEl = document.createElement("div");
  roundEl.className = "round-block";
  roundEl.dataset.roundIndex = msgObj.roundIndex;
  msgObj.bodyWrap.appendChild(roundEl);

  const round = {
    index: msgObj.roundIndex,
    el: roundEl,
    reasoningBlock: null,
    reasoningContent: "",
    textBlock: null,
    textSegment: null,
  };

  msgObj.rounds.push(round);
  msgObj.currentRound = round;
  return round;
}

function getCurrentRound(msgObj) {
  if (!msgObj.currentRound) return startNewRound(msgObj);
  return msgObj.currentRound;
}

function ensureAssistantTextBlock(msgObj) {
  const round = getCurrentRound(msgObj);
  if (round.textBlock && round.textSegment) return round.textBlock;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  round.el.appendChild(bubble);
  const seg = { type: "text", content: "" };
  msgObj.entry.segments.push(seg);
  round.textBlock = bubble; round.textSegment = seg;
  return bubble;
}

function appendAssistantText(msgObj, delta, persist = true) {
  const text = String(delta || ""); if (!text) return;
  const round = getCurrentRound(msgObj);
  const bubble = ensureAssistantTextBlock(msgObj);
  round.textSegment.content += text;
  bubble.innerHTML = renderMarkdown(round.textSegment.content);
  msgObj.hasOutput = true;
  if (persist) { touchConversation(getActiveConversation()); renderConversationList(searchInputEl.value); var convId = state.store.activeConversationId, dbId = _dbId(msgObj.entry); if (convId && dbId) dbAppendText(convId, dbId, text); }
}

function ensureReasoningBlock(msgObj) {
  const round = getCurrentRound(msgObj);
  if (round.reasoningBlock) return round.reasoningBlock;
  const wrapper = document.createElement("div");
  wrapper.className = "reasoning-wrapper";
  const header = document.createElement("div");
  header.className = "reasoning-header";
  header.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg><span>思考过程</span><span class="reasoning-toggle">收起</span>';
  header.onclick = function() {
    const content = wrapper.querySelector(".reasoning-content");
    const toggle = header.querySelector(".reasoning-toggle");
    if (content.style.display === "none") {
      content.style.display = "block";
      toggle.textContent = "收起";
    } else {
      content.style.display = "none";
      toggle.textContent = "展开";
    }
  };
  const content = document.createElement("div");
  content.className = "reasoning-content";
  wrapper.appendChild(header); wrapper.appendChild(content);
  round.el.appendChild(wrapper);
  round.reasoningBlock = content;
  return content;
}

function appendReasoningText(msgObj, delta, persist = true) {
  const text = String(delta || ""); if (!text) return;
  const round = getCurrentRound(msgObj);
  round.reasoningContent += text;
  const block = ensureReasoningBlock(msgObj);
  block.innerHTML = renderMarkdown(round.reasoningContent);
  msgObj.hasOutput = true;
  if (persist) {
    var convId = state.store.activeConversationId, dbId = _dbId(msgObj.entry);
    if (convId && dbId) dbAppendReasoning(convId, dbId, text);
  }
}

function renderToolCall(msgObj, payload, persist = true) {
  const round = getCurrentRound(msgObj);
  round.textBlock = null; round.textSegment = null;
  const toolName = String(payload.name || "tool");
  const argsObj = payload.args && typeof payload.args === "object" ? payload.args : {};
  const seg = { type: "tool_call", name: toolName, args: argsObj, result: "" };
  msgObj.entry.segments.push(seg);
  const { details, resultBlock } = createToolDetails(toolName, argsObj, "等待工具返回...");
  round.el.appendChild(details);
  msgObj.toolCalls.push({ name: toolName, resultBlock, done: false, segment: seg });
  msgObj.hasOutput = true;
  if (persist) { touchConversation(getActiveConversation()); renderConversationList(searchInputEl.value); var convId = state.store.activeConversationId, dbId = _dbId(msgObj.entry); if (convId && dbId) dbAddToolCall(convId, dbId, toolName, argsObj); }
}

function renderToolResult(msgObj, payload, persist = true) {
  const matched = msgObj.toolCalls.find((i) => i.name === String(payload.name || "") && !i.done) || msgObj.toolCalls.find((i) => !i.done);
  if (!matched) return;
  const rt = String(payload.result || "");
  if (isRagTextResult(rt)) {
    if (!matched.resultBlock.classList.contains("rag-result-container")) {
      var newBlock = document.createElement("div");
      newBlock.className = "rag-result-container";
      matched.resultBlock.replaceWith(newBlock);
      matched.resultBlock = newBlock;
    }
    renderRagQueryResult(matched.resultBlock, rt);
  } else {
    matched.resultBlock.textContent = rt.slice(0, 4000);
  }
  matched.segment.result = rt; matched.done = true;
  if (persist) { touchConversation(getActiveConversation()); renderConversationList(searchInputEl.value); var convId = state.store.activeConversationId, dbId = _dbId(msgObj.entry); if (convId && dbId) dbSetToolResult(convId, dbId, rt); }
}

function isRagTextResult(text) {
  return /命中片段/.test(text) && /来源:.*\|.*chunk:.*\|.*hybrid:/m.test(text);
}

function parseRagText(rawText) {
  var lines = rawText.split("\n");
  var meta = { query: "", count: "", strategy: "", timing: "", rewriteSummary: "", rewriteVariants: [] };
  var chunks = [];
  var inChunks = false;
  var currentChunk = null;
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i];
    if (/^命中片段\s*:/.test(line)) { inChunks = true; continue; }
    if (!inChunks) {
      if (/^最终查询\s*:/.test(line)) meta.query = line.replace(/^最终查询\s*:\s*/, "");
      else if (/^命中数量\s*:/.test(line)) meta.count = line.replace(/^命中数量\s*:\s*/, "");
      else if (/^自动改写检索\s*:/.test(line)) meta.rewriteSummary = line.replace(/^自动改写检索\s*:\s*/, "");
      else if (/^-\s*第\d+路\s*\|/.test(line)) meta.rewriteVariants.push(line.replace(/^\s*-\s*/, ""));
      else if (/^检索策略\s*:/.test(line)) meta.strategy = line.replace(/^检索策略\s*:\s*/, "");
      else if (/^检索耗时\s*:/.test(line)) meta.timing = line.replace(/^检索耗时\s*:\s*/, "");
    } else {
      var headerMatch = line.match(/^\s*(\d+)\.\s+来源:\s*(.+?)\s*\|\s*chunk:\s*(.+?)\s*\|\s*hybrid:\s*([\d.]+)/);
      if (headerMatch) {
        if (currentChunk) chunks.push(currentChunk);
        currentChunk = { index: parseInt(headerMatch[1]), source: headerMatch[2], chunkId: headerMatch[3], hybrid: parseFloat(headerMatch[4]), text: "" };
        continue;
      }
      if (currentChunk && /^\s+内容:\s*/.test(line)) {
        currentChunk.text += line.replace(/^\s+内容:\s*/, "") + "\n";
      } else if (currentChunk && !headerMatch && line.trim()) {
        currentChunk.text += line + "\n";
      }
    }
  }
  if (currentChunk) chunks.push(currentChunk);
  return { meta: meta, chunks: chunks };
}

function renderRagQueryResult(container, rawText) {
  container.innerHTML = "";
  var parsed = parseRagText(rawText);

  var metaEl = document.createElement("div");
  metaEl.className = "rag-meta";
  if (parsed.meta.query) { var m = document.createElement("span"); m.className = "rag-meta-item"; m.textContent = "\u6700\u7EC8\u67E5\u8BE2: " + parsed.meta.query; metaEl.appendChild(m); }
  if (parsed.meta.count) { var c = document.createElement("span"); c.className = "rag-meta-item"; c.textContent = "\u547D\u4E2D\u6570\u91CF: " + parsed.meta.count; metaEl.appendChild(c); }
  container.appendChild(metaEl);

  if (parsed.meta.rewriteSummary || (parsed.meta.rewriteVariants && parsed.meta.rewriteVariants.length)) {
    var rewriteEl = document.createElement("div");
    rewriteEl.className = "rag-rewrite-block";

    if (parsed.meta.rewriteSummary) {
      var rewriteTitle = document.createElement("div");
      rewriteTitle.className = "rag-rewrite-title";
      rewriteTitle.textContent = "\u81EA\u52A8\u6539\u5199\u68C0\u7D22: " + parsed.meta.rewriteSummary;
      rewriteEl.appendChild(rewriteTitle);
    }

    if (parsed.meta.rewriteVariants && parsed.meta.rewriteVariants.length) {
      var rewriteList = document.createElement("div");
      rewriteList.className = "rag-rewrite-list";
      parsed.meta.rewriteVariants.forEach(function(item) {
        var variantEl = document.createElement("div");
        variantEl.className = "rag-rewrite-item";
        variantEl.textContent = item;
        rewriteList.appendChild(variantEl);
      });
      rewriteEl.appendChild(rewriteList);
    }

    container.appendChild(rewriteEl);
  }

  if (parsed.meta.strategy) {
    var stratEl = document.createElement("div"); stratEl.className = "rag-timing"; stratEl.textContent = parsed.meta.strategy;
    container.appendChild(stratEl);
  }

  if (parsed.meta.timing) {
    var timingEl = document.createElement("div"); timingEl.className = "rag-timing"; timingEl.textContent = parsed.meta.timing;
    container.appendChild(timingEl);
  }

  if (!parsed.chunks.length) { var empty = document.createElement("div"); empty.className = "rag-empty"; empty.textContent = "\u672A\u68C0\u7D22\u5230\u76F8\u5173\u7247\u6BB5"; container.appendChild(empty); return; }

  var listEl = document.createElement("div");
  listEl.className = "rag-chunk-list";
  parsed.chunks.forEach(function(item, idx) {
    var chunkEl = document.createElement("div");
    chunkEl.className = "rag-chunk-item";
    chunkEl.setAttribute("data-index", idx);

    var headerEl = document.createElement("div");
    headerEl.className = "rag-chunk-header";
    headerEl.innerHTML =
      '<span class="rag-chunk-num">' + item.index + '</span>' +
      '<span class="rag-chunk-source">' + escapeHtml(item.source || "\u672A\u77E5") + '</span>' +
      '<span class="rag-chunk-scores">hybrid: ' + Number(item.hybrid).toFixed(4) + '</span>' +
      '<svg class="rag-chunk-expand" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></svg>';

    var previewEl = document.createElement("div");
    previewEl.className = "rag-chunk-preview";
    var text = (item.text || "").replace(/\n/g, " ").trim();
    previewEl.textContent = text.length > 120 ? text.slice(0, 120) + "..." : text;

    chunkEl.appendChild(headerEl);
    chunkEl.appendChild(previewEl);
    chunkEl.addEventListener("click", function() { openRagChunkOverlay(item, idx, parsed.chunks); });

    listEl.appendChild(chunkEl);
  });
  container.appendChild(listEl);
}

/* ========== RAG Chunk Overlay ========== */
var _ragOverlayState = { items: [], index: -1 };

function openRagChunkOverlay(item, idx, allItems) {
  _ragOverlayState.items = allItems || [];
  _ragOverlayState.index = idx;
  var overlay = document.getElementById("ragChunkOverlay");
  if (!overlay) return;
  showRagOverlayItem();
  overlay.style.display = "flex";
  requestAnimationFrame(function() { overlay.classList.add("visible"); });
  document.body.style.overflow = "hidden";
}

function closeRagChunkOverlay() {
  var overlay = document.getElementById("ragChunkOverlay");
  if (!overlay) return;
  overlay.classList.remove("visible");
  setTimeout(function() {
    overlay.style.display = "none";
    document.body.style.overflow = "";
  }, 200);
  _ragOverlayState.items = [];
  _ragOverlayState.index = -1;
}

function showRagOverlayItem() {
  var item = _ragOverlayState.items[_ragOverlayState.index];
  if (!item) return;

  var titleEl = document.getElementById("ragOverlayTitle");
  var indexEl = document.getElementById("ragOverlayIndex");
  var metaEl = document.getElementById("ragOverlayMeta");
  var contentEl = document.getElementById("ragOverlayContent");
  var prevBtn = document.getElementById("ragOverlayPrev");
  var nextBtn = document.getElementById("ragOverlayNext");

  if (titleEl) titleEl.textContent = escapeHtml(item.source || "\u7247\u6BB5\u8BE6\u60C5");
  if (indexEl) indexEl.textContent = (_ragOverlayState.index + 1) + " / " + _ragOverlayState.items.length;

  if (metaEl) {
    var metaHtml = "";
    metaHtml += '<span class="rag-overlay-meta-item"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg> ' + escapeHtml(item.source || "-") + '</span>';
    if (item.chunkId) metaHtml += '<span class="rag-overlay-meta-item"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg> chunk: ' + escapeHtml(String(item.chunkId)) + '</span>';
    if (item.hybrid != null) {
      metaHtml += '<span class="rag-overlay-meta-item rag-score">hybrid: <strong>' + Number(item.hybrid).toFixed(4) + '</strong></span>';
    }
    metaEl.innerHTML = metaHtml;
  }

  if (contentEl) contentEl.textContent = item.text || "\uFF08\u65E0\u5185\u5BB9\uFF09";

  if (prevBtn) prevBtn.disabled = _ragOverlayState.index <= 0;
  if (nextBtn) nextBtn.disabled = _ragOverlayState.index >= _ragOverlayState.items.length - 1;
}

function initRagOverlayEvents() {
  var overlay = document.getElementById("ragChunkOverlay");
  if (!overlay) return;

  overlay.querySelector(".rag-overlay-backdrop").addEventListener("click", closeRagChunkOverlay);
  document.getElementById("ragOverlayClose").addEventListener("click", closeRagChunkOverlay);
  document.getElementById("ragOverlayPrev").addEventListener("click", function() {
    if (_ragOverlayState.index > 0) { _ragOverlayState.index--; showRagOverlayItem(); }
  });
  document.getElementById("ragOverlayNext").addEventListener("click", function() {
    if (_ragOverlayState.index < _ragOverlayState.items.length - 1) { _ragOverlayState.index++; showRagOverlayItem(); }
  });

  document.addEventListener("keydown", function(e) {
    if (!overlay || overlay.style.display === "none") return;
    if (e.key === "Escape") closeRagChunkOverlay();
    else if (e.key === "ArrowLeft" && _ragOverlayState.index > 0) { _ragOverlayState.index--; showRagOverlayItem(); }
    else if (e.key === "ArrowRight" && _ragOverlayState.index < _ragOverlayState.items.length - 1) { _ragOverlayState.index++; showRagOverlayItem(); }
  });
}

function renderTokenStats(msgObj, payload, persist = true) {
  const ts = { input_tokens: Number(payload.input_tokens || 0), output_tokens: Number(payload.output_tokens || 0), llm_calls: Number(payload.llm_calls || 0) };
  const total = ts.input_tokens + ts.output_tokens;
  const node = document.createElement("div");
  node.className = "token-block";
  node.textContent = `\u8F93\u5165 ${ts.input_tokens} | \u8F93\u51FA ${ts.output_tokens} | \u5408\u8BA1 ${total} | LLM\u8C03\u7528 ${ts.llm_calls}`;
  msgObj.statsWrap.innerHTML = ""; msgObj.statsWrap.appendChild(node);
  msgObj.entry.token_stats = ts;
  if (persist) { touchConversation(getActiveConversation()); renderConversationList(searchInputEl.value); var convId = state.store.activeConversationId, dbId = _dbId(msgObj.entry); if (convId && dbId) dbSetTokenStats(convId, dbId, ts); }
}

function renderAssistantFromHistory(entry) {
  console.log('[renderFromHistory] 恢复消息', { segments: (entry.segments || []).length, hasTokenStats: !!entry.token_stats });
  const msgObj = createAssistantMessageDom(entry);
  const round = startNewRound(msgObj);
  for (const seg of entry.segments || []) {
    if (seg.type === "reasoning") {
      round.reasoningContent = seg.content || "";
      const wrapper = document.createElement("div");
      wrapper.className = "reasoning-wrapper";
      const header = document.createElement("div");
      header.className = "reasoning-header";
      header.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg><span>思考过程</span><span class="reasoning-toggle">收起</span>';
      header.onclick = function() {
        const content = wrapper.querySelector(".reasoning-content");
        const toggle = header.querySelector(".reasoning-toggle");
        if (content.style.display === "none") {
          content.style.display = "block";
          toggle.textContent = "收起";
        } else {
          content.style.display = "none";
          toggle.textContent = "展开";
        }
      };
      const content = document.createElement("div");
      content.className = "reasoning-content";
      content.innerHTML = renderMarkdown(seg.content || "");
      wrapper.appendChild(header); wrapper.appendChild(content);
      round.el.appendChild(wrapper);
      round.reasoningBlock = content;
    } else if (seg.type === "text") {
      const b = document.createElement("div"); b.className = "bubble"; b.innerHTML = renderMarkdown(seg.content || "");
      round.el.appendChild(b);
      round.textBlock = b;
      round.textSegment = seg;
    } else if (seg.type === "tool_call") {
      var resultText = seg.result || "\u7B49\u5F85\u5DE5\u5177\u8FD4\u56DE...";
      if (isRagTextResult(resultText)) {
        var tempDetails = createToolDetails(seg.name || "tool", seg.args || {}, resultText);
        if (tempDetails.resultBlock.classList.contains("rag-result-container")) {
          renderRagQueryResult(tempDetails.resultBlock, resultText);
        }
        round.el.appendChild(tempDetails.details);
        msgObj.toolCalls.push({ name: seg.name || "tool", resultBlock: tempDetails.resultBlock, done: true, segment: seg });
      } else {
        const { details, resultBlock } = createToolDetails(seg.name || "tool", seg.args || {}, resultText);
        round.el.appendChild(details);
        msgObj.toolCalls.push({ name: seg.name || "tool", resultBlock: resultBlock, done: true, segment: seg });
      }
    }
  }
  if (entry.token_stats) renderTokenStats(msgObj, entry.token_stats, false);
}

function renderActiveConversationMessages() {
  messagesEl.innerHTML = "";
  const conv = getActiveConversation();
  console.log('[renderActiveMsgs] 渲染对话', { msgs: (conv.messages && conv.messages.length) || 0, convId: conv.id });
  if (!conv.messages || !conv.messages.length) { renderWelcome(); scrollToBottom(); return; }
  for (const msg of conv.messages) {
    if (msg.role === "user") renderUserMessageDom(msg.content || "");
    else if (msg.role === "assistant") renderAssistantFromHistory(msg);
  }
  scrollToBottom();
}

async function appendUserMessage(text) {
  const conv = getActiveConversation();
  var msg = { role: "user", content: text };
  conv.messages.push(msg);
  if (conv.messages.length > MAX_MESSAGES_PER_CONVERSATION) conv.messages = conv.messages.slice(-MAX_MESSAGES_PER_CONVERSATION);
  touchConversation(conv); renderConversationList(searchInputEl.value);
  renderUserMessageDom(text); scrollToBottom();
  var dbMsg = await dbAppendUserMessage(conv.id, text);
  if (dbMsg) msg.dbId = dbMsg.id;
}

function createAssistantMessage() {
  const conv = getActiveConversation();
  const entry = createAssistantMessageEntry();
  conv.messages.push(entry);
  if (conv.messages.length > MAX_MESSAGES_PER_CONVERSATION) conv.messages = conv.messages.slice(-MAX_MESSAGES_PER_CONVERSATION);
  touchConversation(conv); renderConversationList(searchInputEl.value);
  const msgObj = createAssistantMessageDom(entry); scrollToBottom();
  dbCreateAssistantMessage(conv.id).then(function(dbMsg) { if (dbMsg) entry.dbId = dbMsg.id; });
  return msgObj;
}

function parseSSEChunk(chunk) {
  if (!chunk.trim()) return null;
  const lines = chunk.split("\n");
  let event = "message"; const dataParts = [];
  for (const line of lines) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataParts.push(line.slice(5).trim());
  }
  if (!dataParts.length) return { event, payload: {} };
  try { return { event, payload: JSON.parse(dataParts.join("\n")) }; }
  catch (err) { return { event: "error", payload: { message: `\u6570\u636E\u89E3\u6790\u5931\u8D25: ${err}` } }; }
}

async function consumeStream(response, msgObj) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n"); buffer = chunks.pop() || "";
    for (const rawChunk of chunks) {
      const parsed = parseSSEChunk(rawChunk);
      if (!parsed) continue;
      const { event, payload } = parsed;
      if (event === "content") appendAssistantText(msgObj, payload.delta);
      else if (event === "reasoning") appendReasoningText(msgObj, payload.delta);
      else if (event === "phase") {
        const phaseType = payload && payload.type;
        if (phaseType === "thinking") startNewRound(msgObj);
      }
      else if (event === "tool_call") renderToolCall(msgObj, payload);
      else if (event === "tool_result") renderToolResult(msgObj, payload);
      else if (event === "token_stats") renderTokenStats(msgObj, payload);
      else if (event === "done") return;
      else if (event === "error") appendAssistantText(msgObj, `\u274C ${payload.message}`);
    }
    scrollToBottom();
  }
}

async function refreshState() {
  try {
    const res = await fetch("/api/chat/state");
    const data = await res.json();
    if (!data.ok) return;
  } catch (_) {}
}

async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text || state.generating) return;
  const welcomeEl = messagesEl.querySelector(".messages-empty");
  if (welcomeEl) {
    welcomeEl.classList.add("hiding");
    setTimeout(() => welcomeEl.remove(), 380);
  }
  appendUserMessage(text); inputEl.value = ""; inputEl.style.height = "auto";
  const msgObj = createAssistantMessage(); state.currentAssistant = msgObj;
  state.abortController = new AbortController(); setGenerating(true);

  try {
    const response = await fetch("/api/chat/stream", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }), signal: state.abortController.signal,
    });
    if (!response.ok) {
      const p = await response.json().catch(() => ({ message: `\u8BF7\u6C42\u5931\u8D25(${response.status})` }));
      appendAssistantText(msgObj, `\u274C ${p.message || "\u8BF7\u6C42\u5931\u8D25"}`); return;
    }
    await consumeStream(response, msgObj);
    if (!msgObj.hasOutput) appendAssistantText(msgObj, "(\u65E0\u8F93\u51FA)");
  } catch (err) {
    if (err.name === "AbortError") { if (!msgObj.hasOutput) appendAssistantText(msgObj, "\u23F9\uFEF0 \u5DF2\u505C\u6B62\u751F\u6210"); }
    else appendAssistantText(msgObj, `\n\n\u274C ${err}`);
  } finally {
    state.abortController = null; state.currentAssistant = null; setGenerating(false);
    touchConversation(getActiveConversation()); refreshState();
  }
}

function stopMessage() {
  if (!state.generating) return;
  if (state.abortController) state.abortController.abort();
  setGenerating(false);
}

async function switchConversation(id) {
  if (state.generating) { showToast("当前正在生成，请先停止后切换。", "warning"); return; }
  if (id === state.store.activeConversationId) return;
  if (!state.store.conversations.some((c) => c.id === id)) return;
  state.store.activeConversationId = id;
  renderConversationList(searchInputEl.value);
  await loadActiveConversationMessages();
  renderActiveConversationMessages();
  _chatApi.activateConversation(id).catch(function(){});
  toggleSidebar(false);
}

async function createNewConversation() {
  if (state.generating) { showToast("当前正在生成，请先停止后新建。", "warning"); return; }
  var conv = await dbCreateConversation("新对话");
  state.store.conversations.unshift(conv); state.store.activeConversationId = conv.id;
  renderConversationList(searchInputEl.value); renderActiveConversationMessages();
  try { await fetch("/api/chat/reset", { method: "POST" }); } catch (_) {}
  await refreshState(); toggleSidebar(false);
}

async function deleteConversation(id) {
  if (state.generating) { showToast("当前正在生成，请先停止后删除。", "warning"); return; }
  const idx = state.store.conversations.findIndex((c) => c.id === id);
  if (idx < 0) return;
  const deletingActive = id === state.store.activeConversationId;
  await _chatApi.deleteConversation(id).catch(function(){});
  state.store.conversations.splice(idx, 1);
  if (!state.store.conversations.length) { var f = await dbCreateConversation("新对话"); state.store.conversations.push(f); state.store.activeConversationId = f.id; }
  else if (deletingActive) { var next = [...state.store.conversations].sort((a, b) => b.updatedAt - a.updatedAt)[0]; state.store.activeConversationId = next.id; }
  renderConversationList(searchInputEl.value); renderActiveConversationMessages();
  if (deletingActive) try { await fetch("/api/chat/reset", { method: "POST" }); } catch (_) {}
  showToast("对话已删除", "success");
}

async function handleResetMemory() {
  if (state.generating) { showToast("当前正在生成，请先停止。", "warning"); return; }
  showModal(
    "\u6E05\u7A7A\u8BB0\u5FC6",
    "\u786E\u5B9A\u8981\u6E05\u7A7A\u5F53\u524D\u4F1A\u8BDD\u8BB0\u5FC6\u5417\uFF1F",
    async () => {
      try { await fetch("/api/chat/reset", { method: "POST" }); } catch (_) {}
      renderActiveConversationMessages(); await refreshState();
      showToast("\u8BB0\u5FC6\u5DF2\u6E07\u7A7A", "success");
    }
  );
}


/* ========== Batch Mode ========== */
function toggleBatchSelect(id) {
  if (state.batchSelected.has(id)) { state.batchSelected.delete(id); }
  else { state.batchSelected.add(id); }
  updateBatchUI();
}

function updateBatchUI() {
  batchCountEl.textContent = String(state.batchSelected.size);
  renderConversationList(searchInputEl.value);
}

function enterBatchMode() {
  state.batchMode = true;
  state.batchSelected.clear();
  batchActionBar.style.display = "flex";
  newConversationBtn.disabled = true;
  updateBatchUI();
}

function exitBatchMode() {
  state.batchMode = false;
  state.batchSelected.clear();
  batchActionBar.style.display = "none";
  newConversationBtn.disabled = false;
  updateBatchUI();
}

function selectAllBatch() {
  const allIds = state.store.conversations.map((c) => c.id);
  if (state.batchSelected.size >= allIds.length) {
    state.batchSelected.clear();
  } else {
    allIds.forEach((id) => state.batchSelected.add(id));
  }
  updateBatchUI();
}

async function deleteSelectedBatch() {
  if (!state.batchSelected.size) return;
  const count = state.batchSelected.size;
  showModal(
    "批量删除",
    `确定要删除选中的 <strong>${count}</strong> 个对话吗？此操作不可撤销。`,
    async () => {
      var ids = [...state.batchSelected];
      await _chatApi.batchDeleteConversations(ids).catch(function(){});
      state.store.conversations = state.store.conversations.filter(function(c) { return !ids.includes(c.id); });
      state.batchSelected.clear();
      if (!state.store.conversations.length) { var f = await dbCreateConversation("新对话"); state.store.conversations.push(f); state.store.activeConversationId = f.id; }
      else if (!state.store.activeConversationId || ids.includes(state.store.activeConversationId)) { state.store.activeConversationId = state.store.conversations[0].id; }
      exitBatchMode();
      renderConversationList(searchInputEl.value); renderActiveConversationMessages();
      showToast("已删除 " + count + " 个对话", "success");
    }
  );
}


/* ========== Event Bindings ========== */
sendStopBtn.addEventListener("click", () => { if (state.generating) stopMessage(); else sendMessage(); });
newConversationBtn.addEventListener("click", () => createNewConversation());
resetMemoryBtn.addEventListener("click", () => handleResetMemory());
batchModeBtn.addEventListener("click", () => {
  if (state.batchMode) exitBatchMode();
  else enterBatchMode();
});
batchSelectAllBtn.addEventListener("click", selectAllBatch);
batchDeleteBtn.addEventListener("click", deleteSelectedBatch);
batchCancelBtn.addEventListener("click", exitBatchMode);

inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (!state.generating) sendMessage(); }
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && state.batchMode) { exitBatchMode(); return; }
  if ((e.key === "/" || e.key === "Escape") && document.activeElement !== inputEl) {
    if (e.key === "/") { e.preventDefault(); inputEl.focus(); }
    if (e.key === "Escape" && sidebarEl.classList.contains("open")) toggleSidebar(false);
  }
});


/* ========== Init ========== */
async function init() {
  await loadStoreFromAPI();
  await loadActiveConversationMessages();
  renderConversationList(); renderActiveConversationMessages();
  pollKbIngestStatus();
  initRagOverlayEvents();
}

var _kbPollTimer = null;
function pollKbIngestStatus() {
  if (_kbPollTimer) clearInterval(_kbPollTimer);
  _kbPollTimer = setInterval(function () {
    var badge = document.getElementById("kbIngestBadge");
    if (!badge) { clearInterval(_kbPollTimer); return; }
    fetch("/api/kb/jobs/active").then(function (r) { return r.json(); }).then(function (data) {
      if (!badge) return;
      if (data.ok && data.jobs && data.jobs.length > 0) {
        badge.style.display = "inline-flex";
      } else {
        badge.style.display = "none";
      }
    }).catch(function () {});
  }, 5000);
  setTimeout(function () { fetch("/api/kb/jobs/active").then(function (r) { return r.json(); }).then(function (data) {
    var badge = document.getElementById("kbIngestBadge");
    if (badge && data.ok && data.jobs && data.jobs.length > 0) badge.style.display = "inline-flex";
  }); }, 500);
}

init();
