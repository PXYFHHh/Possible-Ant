const uploadFormEl = document.getElementById("uploadForm");
const uploadInputEl = document.getElementById("uploadInput");
const uploadButtonEl = document.getElementById("uploadButton");
const uploadResultEl = document.getElementById("uploadResult");
const docsBodyEl = document.getElementById("docsTableBody");
const docsEmptyEl = document.getElementById("docsEmpty");
const refreshDocsBtn = document.getElementById("refreshDocsButton");
const refreshHealthBtn = document.getElementById("refreshHealthButton");
const healthOutputEl = document.getElementById("healthOutput");

function setUploadResult(message, ok) {
  uploadResultEl.textContent = message;
  uploadResultEl.classList.remove("success", "error");
  uploadResultEl.classList.add(ok ? "success" : "error");
}

function renderDocuments(documents) {
  docsBodyEl.innerHTML = "";
  if (!documents.length) {
    docsEmptyEl.style.display = "block";
    return;
  }

  docsEmptyEl.style.display = "none";
  for (const doc of documents) {
    const row = document.createElement("tr");

    const sourceCell = document.createElement("td");
    sourceCell.textContent = doc.source || "-";

    const chunkCell = document.createElement("td");
    chunkCell.textContent = String(doc.chunk_count ?? 0);

    const updatedCell = document.createElement("td");
    updatedCell.textContent = doc.updated_at || "-";

    const actionCell = document.createElement("td");
    const deleteBtn = document.createElement("button");
    deleteBtn.className = "danger-btn";
    deleteBtn.type = "button";
    deleteBtn.textContent = "删除";
    deleteBtn.addEventListener("click", () => {
      deleteDocument(doc.source || "");
    });
    actionCell.appendChild(deleteBtn);

    row.appendChild(sourceCell);
    row.appendChild(chunkCell);
    row.appendChild(updatedCell);
    row.appendChild(actionCell);
    docsBodyEl.appendChild(row);
  }
}

async function loadDocuments() {
  const response = await fetch("/api/kb/documents");
  const data = await response.json().catch(() => ({ ok: false, message: "读取失败" }));
  if (!response.ok || !data.ok) {
    docsBodyEl.innerHTML = "";
    docsEmptyEl.style.display = "block";
    docsEmptyEl.textContent = data.message || "读取文档失败";
    return;
  }
  docsEmptyEl.textContent = "暂无文档";
  renderDocuments(data.documents || []);
}

async function deleteDocument(source) {
  if (!source) {
    return;
  }
  const ok = window.confirm(`确认删除文档 ${source} ?`);
  if (!ok) {
    return;
  }

  const response = await fetch(`/api/kb/documents/${encodeURIComponent(source)}`, { method: "DELETE" });
  const data = await response.json().catch(() => ({ ok: false, message: "删除失败" }));
  setUploadResult(data.message || (data.ok ? "删除成功" : "删除失败"), Boolean(data.ok));
  await loadDocuments();
  await loadHealth();
}

async function uploadDocument(file) {
  const form = new FormData();
  form.append("file", file);

  uploadButtonEl.disabled = true;
  setUploadResult("上传中...", true);

  try {
    const response = await fetch("/api/kb/upload", { method: "POST", body: form });
    const data = await response.json().catch(() => ({ ok: false, message: "上传失败" }));
    setUploadResult(data.message || (data.ok ? "上传成功" : "上传失败"), Boolean(data.ok));
    if (data.ok) {
      uploadInputEl.value = "";
      await loadDocuments();
      await loadHealth();
    }
  } finally {
    uploadButtonEl.disabled = false;
  }
}

async function loadHealth() {
  const response = await fetch("/api/kb/health");
  const data = await response.json().catch(() => ({ ok: false, message: "读取失败" }));
  healthOutputEl.textContent = JSON.stringify(data, null, 2);
}

uploadFormEl.addEventListener("submit", (event) => {
  event.preventDefault();
  const file = uploadInputEl.files[0];
  if (!file) {
    setUploadResult("请先选择文件", false);
    return;
  }
  uploadDocument(file);
});

refreshDocsBtn.addEventListener("click", () => {
  loadDocuments();
});

refreshHealthBtn.addEventListener("click", () => {
  loadHealth();
});

loadDocuments();
loadHealth();
