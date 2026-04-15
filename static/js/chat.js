const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("messageInput");
const sendStopBtn = document.getElementById("sendStopButton");
const newConversationBtn = document.getElementById("newConversationButton");
const conversationListEl = document.getElementById("conversationList");
const conversationEmptyEl = document.getElementById("conversationEmpty");
const memoryCountEl = document.getElementById("memoryCount");
const memoryRemainEl = document.getElementById("memoryRemain");
const busyStateEl = document.getElementById("busyState");

const CHAT_STORE_KEY = "agent_chat_store_v2";
const LEGACY_HISTORY_KEY = "agent_chat_history_v1";
const MAX_CONVERSATIONS = 50;
const MAX_MESSAGES_PER_CONVERSATION = 200;

const state = {
  generating: false,
  abortController: null,
  currentAssistant: null,
  store: {
    version: 2,
    activeConversationId: "",
    conversations: [],
  },
};

if (window.marked) {
  window.marked.setOptions({
    gfm: true,
    breaks: true,
  });
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
    const html = window.marked.parse(text);
    return window.DOMPurify.sanitize(html);
  }
  return escapeHtml(text).replaceAll("\n", "<br>");
}

function makeConversationId() {
  return `conv_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function nowTs() {
  return Date.now();
}

function formatTime(ts) {
  const d = new Date(ts || Date.now());
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${y}-${m}-${day} ${hh}:${mm}`;
}

function normalizeAssistantMessage(item) {
  const segments = Array.isArray(item.segments) ? item.segments : [];
  const safeSegments = [];

  for (const seg of segments) {
    if (!seg || typeof seg !== "object") {
      continue;
    }

    if (seg.type === "text") {
      safeSegments.push({
        type: "text",
        content: String(seg.content || ""),
      });
      continue;
    }

    if (seg.type === "tool_call") {
      safeSegments.push({
        type: "tool_call",
        name: String(seg.name || "tool"),
        args: seg.args && typeof seg.args === "object" ? seg.args : {},
        result: String(seg.result || ""),
      });
    }
  }

  const msg = {
    role: "assistant",
    segments: safeSegments,
  };

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
  if (!Array.isArray(rawMessages)) {
    return [];
  }

  const normalized = [];
  for (const item of rawMessages) {
    if (!item || typeof item !== "object") {
      continue;
    }

    if (item.role === "user") {
      normalized.push({ role: "user", content: String(item.content || "") });
      continue;
    }

    if (item.role === "assistant") {
      normalized.push(normalizeAssistantMessage(item));
    }
  }

  if (normalized.length > MAX_MESSAGES_PER_CONVERSATION) {
    return normalized.slice(-MAX_MESSAGES_PER_CONVERSATION);
  }
  return normalized;
}

function buildConversationTitle(conversation) {
  const firstUser = (conversation.messages || []).find((m) => m.role === "user" && String(m.content || "").trim());
  if (!firstUser) {
    return "新对话";
  }
  const text = String(firstUser.content || "").replace(/\s+/g, " ").trim();
  if (!text) {
    return "新对话";
  }
  return text.length > 24 ? `${text.slice(0, 24)}...` : text;
}

function createEmptyConversation() {
  const ts = nowTs();
  return {
    id: makeConversationId(),
    title: "新对话",
    createdAt: ts,
    updatedAt: ts,
    messages: [],
  };
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

  if (!conv.title || conv.title === "新对话") {
    conv.title = buildConversationTitle(conv);
  }

  return conv;
}

function migrateLegacyHistoryIfNeeded() {
  try {
    const legacyRaw = window.localStorage.getItem(LEGACY_HISTORY_KEY);
    if (!legacyRaw) {
      return null;
    }

    const legacyParsed = JSON.parse(legacyRaw);
    const legacyMessages = normalizeMessages(legacyParsed);
    window.localStorage.removeItem(LEGACY_HISTORY_KEY);

    if (!legacyMessages.length) {
      return null;
    }

    const conv = createEmptyConversation();
    conv.messages = legacyMessages;
    conv.title = buildConversationTitle(conv);
    conv.updatedAt = nowTs();

    return {
      version: 2,
      activeConversationId: conv.id,
      conversations: [conv],
    };
  } catch (_) {
    return null;
  }
}

function ensureStoreValid(storeLike) {
  const store = {
    version: 2,
    activeConversationId: "",
    conversations: [],
  };

  if (storeLike && Array.isArray(storeLike.conversations)) {
    const dedup = new Map();
    for (const raw of storeLike.conversations) {
      if (!raw || typeof raw !== "object") {
        continue;
      }
      const conv = normalizeConversation(raw);
      dedup.set(conv.id, conv);
    }
    store.conversations = Array.from(dedup.values());
  }

  if (!store.conversations.length) {
    store.conversations.push(createEmptyConversation());
  }

  if (store.conversations.length > MAX_CONVERSATIONS) {
    store.conversations.sort((a, b) => b.updatedAt - a.updatedAt);
    store.conversations = store.conversations.slice(0, MAX_CONVERSATIONS);
  }

  const preferred = String(storeLike?.activeConversationId || "").trim();
  const hasPreferred = store.conversations.some((c) => c.id === preferred);
  store.activeConversationId = hasPreferred ? preferred : store.conversations[0].id;

  return store;
}

function loadStore() {
  const migrated = migrateLegacyHistoryIfNeeded();
  if (migrated) {
    return ensureStoreValid(migrated);
  }

  try {
    const raw = window.localStorage.getItem(CHAT_STORE_KEY);
    if (!raw) {
      return ensureStoreValid(null);
    }
    const parsed = JSON.parse(raw);
    return ensureStoreValid(parsed);
  } catch (_) {
    return ensureStoreValid(null);
  }
}

function saveStore() {
  state.store = ensureStoreValid(state.store);
  try {
    window.localStorage.setItem(CHAT_STORE_KEY, JSON.stringify(state.store));
  } catch (_) {
    // ignore localStorage write errors
  }
}

function getActiveConversation() {
  const id = state.store.activeConversationId;
  const conv = state.store.conversations.find((c) => c.id === id);
  if (conv) {
    return conv;
  }

  const fallback = createEmptyConversation();
  state.store.conversations.unshift(fallback);
  state.store.activeConversationId = fallback.id;
  saveStore();
  return fallback;
}

function touchConversation(conversation) {
  conversation.updatedAt = nowTs();
  conversation.title = buildConversationTitle(conversation);
}

function flattenAssistantMessageToText(msg) {
  if (!msg || typeof msg !== "object") {
    return "";
  }
  const segs = Array.isArray(msg.segments) ? msg.segments : [];
  const parts = [];

  for (const seg of segs) {
    if (!seg || typeof seg !== "object") {
      continue;
    }
    if (seg.type === "text") {
      const text = String(seg.content || "").trim();
      if (text) {
        parts.push(text);
      }
    } else if (seg.type === "tool_call") {
      const name = String(seg.name || "tool").trim();
      const result = String(seg.result || "").trim();
      if (result) {
        parts.push(`[工具 ${name} 返回]\n${result}`);
      }
    }
  }
  return parts.join("\n\n").trim();
}

function conversationForSync(conversation) {
  const payload = [];
  for (const msg of conversation.messages || []) {
    if (msg.role === "user") {
      const text = String(msg.content || "").trim();
      if (text) {
        payload.push({ role: "user", content: text });
      }
      continue;
    }

    if (msg.role === "assistant") {
      const text = flattenAssistantMessageToText(msg);
      if (text) {
        payload.push({ role: "assistant", content: text });
      }
    }
  }
  return payload;
}

async function syncActiveConversationToServer() {
  const conversation = getActiveConversation();
  const payload = conversationForSync(conversation);

  try {
    const response = await fetch("/api/chat/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: payload }),
    });
    if (!response.ok) {
      return;
    }
    await refreshState();
  } catch (_) {
    // ignore sync failure and keep local UI available
  }
}

function setGenerating(flag) {
  state.generating = flag;
  sendStopBtn.textContent = flag ? "停止" : "发送";
  sendStopBtn.classList.toggle("danger", flag);

  if (flag) {
    inputEl.disabled = true;
    busyStateEl.textContent = "生成中";
  } else {
    inputEl.disabled = false;
    inputEl.focus();
    busyStateEl.textContent = "空闲";
  }
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function renderConversationList() {
  conversationListEl.innerHTML = "";
  const sorted = [...state.store.conversations].sort((a, b) => b.updatedAt - a.updatedAt);

  if (!sorted.length) {
    conversationEmptyEl.style.display = "block";
    return;
  }

  conversationEmptyEl.style.display = "none";

  for (const conv of sorted) {
    const li = document.createElement("li");
    const item = document.createElement("div");
    item.className = "conversation-item";
    if (conv.id === state.store.activeConversationId) {
      item.classList.add("active");
    }

    const main = document.createElement("div");
    main.className = "conversation-main";

    const title = document.createElement("div");
    title.className = "conversation-title";
    title.textContent = conv.title || "新对话";

    const meta = document.createElement("div");
    meta.className = "conversation-meta";
    meta.textContent = `${conv.messages.length} 条消息 · ${formatTime(conv.updatedAt)}`;

    main.appendChild(title);
    main.appendChild(meta);
    main.addEventListener("click", () => {
      switchConversation(conv.id);
    });

    const actions = document.createElement("details");
    actions.className = "conversation-actions";

    const trigger = document.createElement("summary");
    trigger.textContent = "...";

    const menu = document.createElement("div");
    menu.className = "conversation-menu";

    const deleteBtn = document.createElement("button");
    deleteBtn.type = "button";
    deleteBtn.className = "conversation-delete-btn";
    deleteBtn.textContent = "删除";
    deleteBtn.addEventListener("pointerdown", (event) => {
      event.stopPropagation();
    });
    deleteBtn.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();

      if (!confirmDeleteConversation(conv.id)) {
        return;
      }

      actions.open = false;
      await deleteConversation(conv.id);
    });

    menu.appendChild(deleteBtn);
    actions.appendChild(trigger);
    actions.appendChild(menu);

    actions.addEventListener("toggle", () => {
      if (!actions.open) {
        return;
      }
      for (const other of document.querySelectorAll(".conversation-actions[open]")) {
        if (other !== actions) {
          other.open = false;
        }
      }
    });
    actions.addEventListener("click", (event) => {
      event.stopPropagation();
    });

    item.appendChild(main);
    item.appendChild(actions);

    li.appendChild(item);
    conversationListEl.appendChild(li);
  }
}

function renderWelcome() {
  const node = document.createElement("div");
  node.className = "message role-assistant";
  node.innerHTML = '<div class="bubble">你好，我是你的本地 Agent 助手。可以直接提问，也可以切到知识库页面上传文档。</div>';
  messagesEl.appendChild(node);
}

function renderUserMessageDom(text) {
  const node = document.createElement("div");
  node.className = "message role-user";
  node.innerHTML = `<div class="bubble">${escapeHtml(text)}</div>`;
  messagesEl.appendChild(node);
}

function createToolDetails(name, args, resultText) {
  const details = document.createElement("details");
  details.className = "tool-block";
  details.open = false;

  const summary = document.createElement("summary");
  summary.textContent = `🔧 ${name || "tool"}`;

  const argsBlock = document.createElement("pre");
  argsBlock.textContent = JSON.stringify(args || {}, null, 2);

  const resultBlock = document.createElement("pre");
  resultBlock.textContent = String(resultText || "等待工具返回...");

  details.appendChild(summary);
  details.appendChild(argsBlock);
  details.appendChild(resultBlock);
  return { details, resultBlock };
}

function createAssistantMessageEntry() {
  return {
    role: "assistant",
    segments: [],
  };
}

function createAssistantMessageDom(entry) {
  const node = document.createElement("div");
  node.className = "message role-assistant";

  const bodyWrap = document.createElement("div");
  bodyWrap.className = "assistant-flow";
  const statsWrap = document.createElement("div");

  node.appendChild(bodyWrap);
  node.appendChild(statsWrap);
  messagesEl.appendChild(node);

  return {
    node,
    bodyWrap,
    statsWrap,
    entry,
    toolCalls: [],
    currentTextBlock: null,
    currentTextSegment: null,
    hasOutput: false,
  };
}

function ensureAssistantTextBlock(msgObj) {
  if (msgObj.currentTextBlock && msgObj.currentTextSegment) {
    return msgObj.currentTextBlock;
  }

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  msgObj.bodyWrap.appendChild(bubble);

  const seg = { type: "text", content: "" };
  msgObj.entry.segments.push(seg);
  msgObj.currentTextBlock = bubble;
  msgObj.currentTextSegment = seg;
  return bubble;
}

function appendAssistantText(msgObj, delta, persist = true) {
  const text = String(delta || "");
  if (!text) {
    return;
  }

  const bubble = ensureAssistantTextBlock(msgObj);
  msgObj.currentTextSegment.content += text;
  bubble.innerHTML = renderMarkdown(msgObj.currentTextSegment.content);
  msgObj.hasOutput = true;

  if (persist) {
    const conv = getActiveConversation();
    touchConversation(conv);
    saveStore();
    renderConversationList();
  }
}

function renderToolCall(msgObj, payload, persist = true) {
  msgObj.currentTextBlock = null;
  msgObj.currentTextSegment = null;

  const toolName = String(payload.name || "tool");
  const argsObj = payload.args && typeof payload.args === "object" ? payload.args : {};

  const seg = {
    type: "tool_call",
    name: toolName,
    args: argsObj,
    result: "",
  };
  msgObj.entry.segments.push(seg);

  const { details, resultBlock } = createToolDetails(toolName, argsObj, "等待工具返回...");
  msgObj.bodyWrap.appendChild(details);
  msgObj.toolCalls.push({ name: toolName, resultBlock, done: false, segment: seg });
  msgObj.hasOutput = true;

  if (persist) {
    const conv = getActiveConversation();
    touchConversation(conv);
    saveStore();
    renderConversationList();
  }
}

function renderToolResult(msgObj, payload, persist = true) {
  const matched =
    msgObj.toolCalls.find((item) => item.name === String(payload.name || "") && !item.done) ||
    msgObj.toolCalls.find((item) => !item.done);
  if (!matched) {
    return;
  }

  const resultText = String(payload.result || "");
  matched.resultBlock.textContent = resultText.slice(0, 4000);
  matched.segment.result = resultText;
  matched.done = true;

  if (persist) {
    const conv = getActiveConversation();
    touchConversation(conv);
    saveStore();
    renderConversationList();
  }
}

function renderTokenStats(msgObj, payload, persist = true) {
  const tokenStats = {
    input_tokens: Number(payload.input_tokens || 0),
    output_tokens: Number(payload.output_tokens || 0),
    llm_calls: Number(payload.llm_calls || 0),
  };

  const total = tokenStats.input_tokens + tokenStats.output_tokens;
  const node = document.createElement("div");
  node.className = "token-block";
  node.textContent = `📊 输入 ${tokenStats.input_tokens} | 输出 ${tokenStats.output_tokens} | 合计 ${total} | LLM调用 ${tokenStats.llm_calls}`;
  msgObj.statsWrap.innerHTML = "";
  msgObj.statsWrap.appendChild(node);

  msgObj.entry.token_stats = tokenStats;

  if (persist) {
    const conv = getActiveConversation();
    touchConversation(conv);
    saveStore();
    renderConversationList();
  }
}

function renderAssistantFromHistory(entry) {
  const msgObj = createAssistantMessageDom(entry);

  for (const seg of entry.segments || []) {
    if (seg.type === "text") {
      const bubble = document.createElement("div");
      bubble.className = "bubble";
      bubble.innerHTML = renderMarkdown(seg.content || "");
      msgObj.bodyWrap.appendChild(bubble);
      continue;
    }

    if (seg.type === "tool_call") {
      const { details } = createToolDetails(seg.name || "tool", seg.args || {}, seg.result || "等待工具返回...");
      msgObj.bodyWrap.appendChild(details);
    }
  }

  if (entry.token_stats) {
    renderTokenStats(msgObj, entry.token_stats, false);
  }
}

function renderActiveConversationMessages() {
  messagesEl.innerHTML = "";
  const conversation = getActiveConversation();

  if (!conversation.messages.length) {
    renderWelcome();
    scrollToBottom();
    return;
  }

  for (const msg of conversation.messages) {
    if (msg.role === "user") {
      renderUserMessageDom(msg.content || "");
    } else if (msg.role === "assistant") {
      renderAssistantFromHistory(msg);
    }
  }
  scrollToBottom();
}

function appendUserMessage(text) {
  const conv = getActiveConversation();
  conv.messages.push({ role: "user", content: text });
  if (conv.messages.length > MAX_MESSAGES_PER_CONVERSATION) {
    conv.messages = conv.messages.slice(-MAX_MESSAGES_PER_CONVERSATION);
  }
  touchConversation(conv);
  saveStore();
  renderConversationList();
  renderUserMessageDom(text);
  scrollToBottom();
}

function createAssistantMessage() {
  const conv = getActiveConversation();
  const entry = createAssistantMessageEntry();
  conv.messages.push(entry);
  if (conv.messages.length > MAX_MESSAGES_PER_CONVERSATION) {
    conv.messages = conv.messages.slice(-MAX_MESSAGES_PER_CONVERSATION);
  }

  touchConversation(conv);
  saveStore();
  renderConversationList();

  const msgObj = createAssistantMessageDom(entry);
  scrollToBottom();
  return msgObj;
}

function parseSSEChunk(chunk) {
  if (!chunk.trim()) {
    return null;
  }

  const lines = chunk.split("\n");
  let event = "message";
  const dataParts = [];

  for (const line of lines) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataParts.push(line.slice(5).trim());
    }
  }

  if (!dataParts.length) {
    return { event, payload: {} };
  }

  try {
    return { event, payload: JSON.parse(dataParts.join("\n")) };
  } catch (err) {
    return { event: "error", payload: { message: `数据解析失败: ${err}` } };
  }
}

async function consumeStream(response, msgObj) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() || "";

    for (const rawChunk of chunks) {
      const parsed = parseSSEChunk(rawChunk);
      if (!parsed) {
        continue;
      }

      const { event, payload } = parsed;
      if (event === "content") {
        appendAssistantText(msgObj, payload.delta || "");
      } else if (event === "tool_call") {
        renderToolCall(msgObj, payload);
      } else if (event === "tool_result") {
        renderToolResult(msgObj, payload);
      } else if (event === "token_stats") {
        renderTokenStats(msgObj, payload);
      } else if (event === "error") {
        appendAssistantText(msgObj, `\n\n❌ ${payload.message || "未知错误"}`);
      }
      scrollToBottom();
    }
  }
}

async function refreshState() {
  try {
    const res = await fetch("/api/chat/state");
    const data = await res.json();
    if (!data.ok) {
      return;
    }

    const memory = data.memory || {};
    memoryCountEl.textContent = `${memory.current_count ?? 0}/${memory.max_memory ?? "-"}`;
    memoryRemainEl.textContent = `${memory.remaining ?? "-"}`;
    if (!state.generating) {
      busyStateEl.textContent = data.busy ? "生成中" : "空闲";
    }
  } catch (_) {
    busyStateEl.textContent = "未知";
  }
}

async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text || state.generating) {
    return;
  }

  appendUserMessage(text);
  inputEl.value = "";

  const msgObj = createAssistantMessage();
  state.currentAssistant = msgObj;

  state.abortController = new AbortController();
  setGenerating(true);

  try {
    const response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
      signal: state.abortController.signal,
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({ message: `请求失败(${response.status})` }));
      appendAssistantText(msgObj, `❌ ${payload.message || "请求失败"}`);
      return;
    }

    await consumeStream(response, msgObj);
    if (!msgObj.hasOutput) {
      appendAssistantText(msgObj, "(无输出)");
    }
  } catch (err) {
    if (err.name === "AbortError") {
      if (!msgObj.hasOutput) {
        appendAssistantText(msgObj, "⏹️ 已停止生成");
      }
    } else {
      appendAssistantText(msgObj, `\n\n❌ ${err}`);
    }
  } finally {
    state.abortController = null;
    state.currentAssistant = null;
    setGenerating(false);
    refreshState();
  }
}

function stopMessage() {
  if (!state.generating) {
    return;
  }
  if (state.abortController) {
    state.abortController.abort();
  }
  setGenerating(false);
}

async function switchConversation(conversationId) {
  if (state.generating) {
    alert("当前正在生成，请先停止后再切换对话。");
    return;
  }

  if (conversationId === state.store.activeConversationId) {
    return;
  }

  const exists = state.store.conversations.some((c) => c.id === conversationId);
  if (!exists) {
    return;
  }

  state.store.activeConversationId = conversationId;
  saveStore();
  renderConversationList();
  renderActiveConversationMessages();
  await syncActiveConversationToServer();
}

async function createNewConversation() {
  if (state.generating) {
    alert("当前正在生成，请先停止后再新建对话。");
    return;
  }

  const conv = createEmptyConversation();
  state.store.conversations.unshift(conv);
  state.store.activeConversationId = conv.id;
  saveStore();

  renderConversationList();
  renderActiveConversationMessages();

  try {
    await fetch("/api/chat/reset", { method: "POST" });
  } catch (_) {
    // ignore reset errors
  }
  await refreshState();
}

function confirmDeleteConversation(conversationId) {
  const conv = state.store.conversations.find((c) => c.id === conversationId);
  if (!conv) {
    return false;
  }
  const title = conv.title || "新对话";
  return window.confirm(`确认删除对话：${title} ?`);
}

async function deleteConversation(conversationId) {
  if (state.generating) {
    alert("当前正在生成，请先停止后再删除对话。");
    return;
  }

  const idx = state.store.conversations.findIndex((c) => c.id === conversationId);
  if (idx < 0) {
    return;
  }

  const deletingActive = conversationId === state.store.activeConversationId;
  state.store.conversations.splice(idx, 1);

  if (!state.store.conversations.length) {
    const fresh = createEmptyConversation();
    state.store.conversations.push(fresh);
    state.store.activeConversationId = fresh.id;
  } else if (deletingActive) {
    const next = [...state.store.conversations].sort((a, b) => b.updatedAt - a.updatedAt)[0];
    state.store.activeConversationId = next.id;
  }

  saveStore();
  renderConversationList();
  renderActiveConversationMessages();

  if (deletingActive) {
    await syncActiveConversationToServer();
  } else {
    await refreshState();
  }
}

sendStopBtn.addEventListener("click", () => {
  if (state.generating) {
    stopMessage();
  } else {
    sendMessage();
  }
});

newConversationBtn.addEventListener("click", () => {
  createNewConversation();
});

inputEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    if (!state.generating) {
      sendMessage();
    }
  }
});

async function init() {
  state.store = loadStore();
  saveStore();
  renderConversationList();
  renderActiveConversationMessages();
  await syncActiveConversationToServer();
  await refreshState();
}

init();
