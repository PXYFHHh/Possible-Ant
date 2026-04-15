const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("messageInput");
const sendStopBtn = document.getElementById("sendStopButton");
const resetBtn = document.getElementById("resetChatButton");
const memoryCountEl = document.getElementById("memoryCount");
const memoryRemainEl = document.getElementById("memoryRemain");
const busyStateEl = document.getElementById("busyState");

const state = {
  generating: false,
  abortController: null,
  currentAssistant: null,
};

if (window.marked) {
  window.marked.setOptions({
    gfm: true,
    breaks: true,
  });
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setGenerating(flag) {
  state.generating = flag;
  sendStopBtn.textContent = flag ? "停止" : "发送";
  sendStopBtn.classList.toggle("danger", flag);
  if (!flag) {
    inputEl.disabled = false;
    inputEl.focus();
    busyStateEl.textContent = "空闲";
  } else {
    inputEl.disabled = true;
    busyStateEl.textContent = "生成中";
  }
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function renderMarkdown(rawText) {
  const text = String(rawText || "");
  if (window.marked && window.DOMPurify) {
    const html = window.marked.parse(text);
    return window.DOMPurify.sanitize(html);
  }
  return escapeHtml(text).replaceAll("\n", "<br>");
}

function ensureAssistantTextBlock(msgObj) {
  if (msgObj.currentTextBlock) {
    return msgObj.currentTextBlock;
  }

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  msgObj.bodyWrap.appendChild(bubble);
  msgObj.currentTextBlock = bubble;
  msgObj.currentTextRaw = "";
  return bubble;
}

function appendAssistantText(msgObj, delta) {
  const bubble = ensureAssistantTextBlock(msgObj);
  msgObj.currentTextRaw += String(delta || "");
  bubble.innerHTML = renderMarkdown(msgObj.currentTextRaw);
  msgObj.hasOutput = true;
}

function appendWelcome() {
  if (messagesEl.children.length > 0) {
    return;
  }
  const node = document.createElement("div");
  node.className = "message role-assistant";
  node.innerHTML = '<div class="bubble">你好，我是你的本地 Agent 助手。可以直接提问，也可以切到知识库页面上传文档。</div>';
  messagesEl.appendChild(node);
  scrollToBottom();
}

function appendUserMessage(text) {
  const node = document.createElement("div");
  node.className = "message role-user";
  node.innerHTML = `<div class="bubble">${escapeHtml(text)}</div>`;
  messagesEl.appendChild(node);
  scrollToBottom();
}

function createAssistantMessage() {
  const node = document.createElement("div");
  node.className = "message role-assistant";

  const bodyWrap = document.createElement("div");
  bodyWrap.className = "assistant-flow";
  const statsWrap = document.createElement("div");

  node.appendChild(bodyWrap);
  node.appendChild(statsWrap);
  messagesEl.appendChild(node);
  scrollToBottom();

  return {
    node,
    bodyWrap,
    statsWrap,
    toolCalls: [],
    currentTextBlock: null,
    currentTextRaw: "",
    hasOutput: false,
  };
}

function renderToolCall(msgObj, payload) {
  msgObj.currentTextBlock = null;
  msgObj.currentTextRaw = "";

  const details = document.createElement("details");
  details.className = "tool-block";
  details.open = false;

  const summary = document.createElement("summary");
  summary.textContent = `🔧 ${payload.name || "tool"}`;

  const argsBlock = document.createElement("pre");
  argsBlock.textContent = JSON.stringify(payload.args || {}, null, 2);

  const resultBlock = document.createElement("pre");
  resultBlock.textContent = "等待工具返回...";

  details.appendChild(summary);
  details.appendChild(argsBlock);
  details.appendChild(resultBlock);
  msgObj.bodyWrap.appendChild(details);
  msgObj.toolCalls.push({ name: payload.name || "", resultBlock, done: false });
  msgObj.hasOutput = true;
  scrollToBottom();
}

function renderToolResult(msgObj, payload) {
  const matched = msgObj.toolCalls.find((item) => item.name === (payload.name || "") && !item.done) || msgObj.toolCalls.find((item) => !item.done);
  if (matched) {
    matched.resultBlock.textContent = String(payload.result || "").slice(0, 4000);
    matched.done = true;
  }
  scrollToBottom();
}

function renderTokenStats(msgObj, payload) {
  const total = (payload.input_tokens || 0) + (payload.output_tokens || 0);
  const node = document.createElement("div");
  node.className = "token-block";
  node.textContent = `📊 输入 ${payload.input_tokens || 0} | 输出 ${payload.output_tokens || 0} | 合计 ${total} | LLM调用 ${payload.llm_calls || 0}`;
  msgObj.statsWrap.innerHTML = "";
  msgObj.statsWrap.appendChild(node);
  scrollToBottom();
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

async function resetChat() {
  if (state.generating) {
    stopMessage();
  }
  const response = await fetch("/api/chat/reset", { method: "POST" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.ok) {
    alert(data.message || "重置失败");
    return;
  }
  messagesEl.innerHTML = "";
  appendWelcome();
  refreshState();
}

sendStopBtn.addEventListener("click", () => {
  if (state.generating) {
    stopMessage();
  } else {
    sendMessage();
  }
});

resetBtn.addEventListener("click", () => {
  resetChat();
});

inputEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    if (!state.generating) {
      sendMessage();
    }
  }
});

appendWelcome();
refreshState();
