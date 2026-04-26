(function () {
  "use strict";

  const uploadZone = document.getElementById("uploadZone");
  const uploadInput = document.getElementById("uploadInput");
  const uploadButton = document.getElementById("uploadButton");
  const uploadFileInfo = document.getElementById("uploadFileInfo");
  const uploadFileName = document.getElementById("uploadFileName");
  const uploadFileClear = document.getElementById("uploadFileClear");
  const uploadResult = document.getElementById("uploadResult");

  const docsList = document.getElementById("docsList");
  const docsEmpty = document.getElementById("docsEmpty");
  const docsCount = document.getElementById("docsCount");
  const refreshDocsBtn = document.getElementById("refreshDocsButton");

  const healthOutput = document.getElementById("healthOutput");
  const refreshHealthBtn = document.getElementById("refreshHealthButton");

  const chunksCount = document.getElementById("chunksCount");
  const chunksStatsSummary = document.getElementById("chunksStatsSummary");
  const chunksMin = document.getElementById("chunksMin");
  const chunksMax = document.getElementById("chunksMax");
  const chunksAvg = document.getElementById("chunksAvg");
  const chunksDistribution = document.getElementById("chunksDistribution");
  const chunksEmpty = document.getElementById("chunksEmpty");
  const refreshChunksBtn = document.getElementById("refreshChunksButton");

  const toastContainer = document.getElementById("toastContainer");


  /* ========== Utilities ========== */
  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  function formatTime(isoString) {
    if (!isoString) return "-";
    try {
      const d = new Date(isoString);
      const now = new Date();
      const isToday = d.toDateString() === now.toDateString();
      if (isToday) {
        return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
      }
      return d.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" }) +
             " " + d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
    } catch {
      return isoString;
    }
  }

  function getFileIcon(filename) {
    const ext = (filename || "").split(".").pop().toLowerCase();
    const icons = {
      pdf: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="15" y2="17"/></svg>`,
      docx: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="12" x2="16" y2="12"/><line x1="8" y1="16" x2="14" y2="16"/></svg>`,
      md: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><path d="M9 14l2 2 4-4"/></svg>`,
      txt: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="10" y1="17" x2="14" y2="17"/></svg>`
    };
    return icons[ext] || icons.txt;
  }


  /* ========== Toast ========== */
  let toastCounter = 0;
  function showToast(message, type) {
    toastCounter++;
    const icons = { success: "\u2713", error: "\u2717", info: "\u2139" };
    const el = document.createElement("div");
    el.className = "toast " + (type || "info");
    el.innerHTML = '<span class="toast-icon">' + (icons[type] || "") + '</span><span class="toast-message">' + escapeHtml(message) + "</span>";
    el.dataset.tid = toastCounter;
    toastContainer.appendChild(el);

    setTimeout(function () { el.classList.add("hiding"); setTimeout(function () { el.remove(); }, 220); }, 3000);
    if (toastContainer.children.length > 3) {
      var first = toastContainer.firstChild;
      first.classList.add("hiding");
      setTimeout(function () { first.remove(); }, 220);
    }
  }


  /* ========== Modal ========== */
  function showModal(title, desc, onConfirm) {
    var overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.innerHTML =
      '<div class="modal">' +
        '<div class="modal-title">' + escapeHtml(title) + '</div>' +
        '<div class="modal-desc">' + desc + '</div>' +
        '<div class="modal-actions">' +
          '<button class="btn-modal-cancel">取消</button>' +
          '<button class="btn-modal-danger">确认删除</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(overlay);

    var close = function () { overlay.remove(); document.removeEventListener("keydown", escHandler); };
    var escHandler = function (e) { if (e.key === "Escape") close(); };
    document.addEventListener("keydown", escHandler);
    overlay.addEventListener("click", function (e) { if (e.target === overlay) close(); });
    overlay.querySelector(".btn-modal-cancel").addEventListener("click", close);
    overlay.querySelector(".btn-modal-danger").addEventListener("click", function () { close(); onConfirm?.(); });
  }


  /* ========== Upload Zone Interactions ========== */
  var selectedFile = null;

  function handleFileSelect(file) {
    if (!file) return;

    var maxMB = 50;
    if (file.size > maxMB * 1024 * 1024) {
      showToast("文件大小超过 " + maxMB + "MB 限制", "error");
      uploadInput.value = "";
      selectedFile = null;
      updateUploadUI();
      return;
    }

    selectedFile = file;
    uploadFileName.textContent = file.name + " (" + formatFileSize(file.size) + ")";
    updateUploadUI();
  }

  function updateUploadUI() {
    if (selectedFile) {
      uploadFileInfo.style.display = "flex";
      uploadZone.querySelector(".upload-zone-content").style.display = "none";
      uploadButton.disabled = false;
    } else {
      uploadFileInfo.style.display = "none";
      uploadZone.querySelector(".upload-zone-content").style.display = "";
      uploadButton.disabled = true;
    }
    uploadResult.style.display = "none";
  }

  uploadZone.addEventListener("click", function (e) {
    if (e.target === uploadFileClear || uploadFileClear.contains(e.target)) return;
    uploadInput.click();
  });

  uploadInput.addEventListener("change", function () {
    if (this.files && this.files[0]) {
      handleFileSelect(this.files[0]);
    }
  });

  uploadFileClear.addEventListener("click", function (e) {
    e.stopPropagation();
    uploadInput.value = "";
    selectedFile = null;
    updateUploadUI();
  });


  /* ========== Drag & Drop ========== */
  uploadZone.addEventListener("dragover", function (e) {
    e.preventDefault();
    e.stopPropagation();
    uploadZone.classList.add("dragover");
  });

  uploadZone.addEventListener("dragleave", function (e) {
    e.preventDefault();
    e.stopPropagation();
    uploadZone.classList.remove("dragover");
  });

  uploadZone.addEventListener("drop", function (e) {
    e.preventDefault();
    e.stopPropagation();
    uploadZone.classList.remove("dragover");

    var files = e.dataTransfer && e.dataTransfer.files;
    if (files && files.length > 0) {
      handleFileSelect(files[0]);
    }
  });


  /* ========== Upload ========== */
  var _pollTimer = null;
  var _pollDone = false;

  async function uploadDocument() {
    if (!selectedFile) {
      showToast("请先选择文件", "error");
      return;
    }

    var form = new FormData();
    form.append("file", selectedFile);

    uploadButton.disabled = true;
    uploadButton.textContent = "上传中...";

    try {
      var response = await fetch("/api/kb/upload", { method: "POST", body: form });
      var data = await response.json().catch(function () { return { ok: false, message: "上传失败" }; });

      if (!data.ok) {
        showToast(data.message || "上传失败", "error");
        uploadResult.className = "upload-result error";
        uploadResult.innerHTML = '\u2717 ' + escapeHtml(data.message || "上传失败");
        uploadResult.style.display = "flex";
        return;
      }

      if (data.job_id) {
        startProgressPoll(data.job_id, selectedFile.name);
      } else {
        showToast(data.message || "上传成功", "success");
        uploadResult.className = "upload-result success";
        uploadResult.innerHTML = '\u2713 ' + escapeHtml(data.message || "文档已成功入库");
        uploadResult.style.display = "flex";
        finishUpload();
      }
    } catch (err) {
      showToast("网络错误：" + err.message, "error");
      finishUpload();
    }
  }

  function startProgressPoll(jobId, fileName) {
    uploadButton.disabled = true;
    uploadButton.textContent = "入库中...";
    _pollDone = false;

    uploadResult.className = "upload-result progress";
    uploadResult.style.display = "flex";
    uploadResult.innerHTML =
      '<div class="progress-info">' +
        '<span class="progress-label">正在入库: <strong>' + escapeHtml(fileName) + '</strong></span>' +
        '<span class="progress-text" id="progressText">准备中...</span>' +
      '</div>' +
      '<div class="progress-bar-track"><div class="progress-bar-fill" id="progressBarFill" style="width:0%"></div></div>';

    _pollTimer = setInterval(function () { pollJobStatus(jobId); }, 1500);
    pollJobStatus(jobId);
  }

  async function pollJobStatus(jobId) {
    if (_pollDone) return;
    try {
      var res = await fetch("/api/kb/job/" + encodeURIComponent(jobId));
      var status = await res.json().catch(function () { return {}; });

      if (!status.ok || !status.job_id) return;

      var total = status.total_chunks || 0;
      var done = status.embedded_chunks || 0;
      var pct = total > 0 ? Math.min(Math.round((done / total) * 100), 100) : 0;

      var progressTextEl = document.getElementById("progressText");
      var progressBarFillEl = document.getElementById("progressBarFill");

      if (progressTextEl) {
        if (total > 0) {
          progressTextEl.textContent = done + ' / ' + total + ' chunks (' + pct + '%)';
        } else {
          progressTextEl.textContent = "切片中...";
        }
      }
      if (progressBarFillEl) {
        progressBarFillEl.style.width = pct + "%";
      }

      if (status.status === "done") {
        _pollDone = true;
        clearInterval(_pollTimer);
        _pollTimer = null;
        uploadResult.className = "upload-result success";
        uploadResult.innerHTML = '\u2713 入库完成 - ' + escapeHtml(status.source) + ' (' + (status.chunk_count || 0) + ' chunks)';
        showToast("入库完成！", "success");
        finishUpload();
        loadDocuments();
        loadHealth();
        loadChunksStats();
      } else if (status.status === "failed") {
        _pollDone = true;
        clearInterval(_pollTimer);
        _pollTimer = null;
        uploadResult.className = "upload-result error";
        uploadResult.innerHTML = '\u2717 ' + escapeHtml(status.error_message || "入库失败");
        showToast("入库失败：" + (status.error_message || "未知错误"), "error");
        finishUpload();
      }
    } catch (err) {
      // silently retry on next tick
    }
  }

  function finishUpload() {
    if (_pollTimer) {
      clearInterval(_pollTimer);
      _pollTimer = null;
    }
    var badge = document.getElementById("kbIngestBadge");
    if (badge) badge.style.display = "none";
    uploadInput.value = "";
    selectedFile = null;
    updateUploadUI();
  }

  uploadButton.addEventListener("click", uploadDocument);


  /* ========== Documents List ========== */
  function renderDocuments(documents) {
    docsList.innerHTML = "";

    if (!documents || !documents.length) {
      docsEmpty.style.display = "";
      docsCount.textContent = "0";
      return;
    }

    docsEmpty.style.display = "none";
    docsCount.textContent = String(documents.length);

    documents.forEach(function (doc) {
      var item = document.createElement("div");
      item.className = "doc-item";

      item.innerHTML =
        '<div class="doc-item-icon">' + getFileIcon(doc.source) + '</div>' +
        '<div class="doc-item-info">' +
          '<div class="doc-item-name">' + escapeHtml(doc.source || "-") + '</div>' +
          '<div class="doc-item-meta">' +
            '<span><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/></svg> ' + String(doc.chunk_count ?? 0) + ' chunks</span>' +
            '<span><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg> ' + formatTime(doc.updated_at) + '</span>' +
          '</div>' +
        '</div>' +
        '<div class="doc-item-actions">' +
          '<button class="btn-delete-doc" data-source="' + escapeHtml(doc.source || "") + '" type="button">删除</button>' +
        '</div>';

      var deleteBtn = item.querySelector(".btn-delete-doc");
      deleteBtn.addEventListener("click", function () {
        var source = this.getAttribute("data-source") || "";
        showModal(
          "确认删除",
          "确定要删除文档 <strong>" + escapeHtml(source) + "</strong> 吗？此操作不可撤销。",
          function () { deleteDocument(source); }
        );
      });

      docsList.appendChild(item);
    });
  }

  async function loadDocuments() {
    try {
      var response = await fetch("/api/kb/documents");
      var data = await response.json().catch(function () { return { ok: false, message: "读取失败" }; });

      if (!response.ok || !data.ok) {
        docsList.innerHTML = "";
        docsEmpty.style.display = "";
        docsEmpty.querySelector("p").textContent = data.message || "读取文档失败";
        docsCount.textContent = "0";
        return;
      }

      docsEmpty.querySelector("p").textContent = "暂无文档";
      renderDocuments(data.documents || []);
    } catch (err) {
      showToast("加载文档列表失败", "error");
    }
  }

  async function deleteDocument(source) {
    if (!source) return;

    try {
      var response = await fetch("/api/kb/documents/" + encodeURIComponent(source), { method: "DELETE" });
      var data = await response.json().catch(function () { return { ok: false, message: "删除失败" }; });

      if (data.ok) {
        showToast("文档已删除", "success");
      } else {
        showToast(data.message || "删除失败", "error");
      }

      await loadDocuments();
      await loadHealth();
      loadChunksStats();
    } catch (err) {
      showToast("删除失败：" + err.message, "error");
    }
  }

  refreshDocsBtn.addEventListener("click", function () {
    loadDocuments();
    this.style.transform = "rotate(360deg)";
    setTimeout(function () { refreshDocsBtn.style.transform = ""; }, 300);
  });


  /* ========== Health Status ========== */
  async function loadHealth() {
    try {
      var response = await fetch("/api/kb/health");
      var data = await response.json().catch(function () { return { ok: false, message: "读取失败" }; });
      healthOutput.textContent = JSON.stringify(data, null, 2);
    } catch (err) {
      healthOutput.textContent = JSON.stringify({ error: err.message }, null, 2);
    }
  }

  refreshHealthBtn.addEventListener("click", function () {
    loadHealth();
    this.style.transform = "rotate(360deg)";
    setTimeout(function () { refreshHealthBtn.style.transform = ""; }, 300);
  });


  /* ========== Chunks Distribution ========== */
  async function loadChunksStats() {
    try {
      var response = await fetch("/api/kb/chunks/stats");
      var data = await response.json();
      if (!data.ok) {
        chunksEmpty.style.display = "block";
        chunksDistribution.style.display = "none";
        chunksStatsSummary.style.display = "none";
        return;
      }
      var stats = data.stats;
      chunksCount.textContent = stats.total || 0;
      if (!stats.total || stats.total === 0) {
        chunksEmpty.style.display = "block";
        chunksDistribution.style.display = "none";
        chunksStatsSummary.style.display = "none";
        return;
      }
      chunksEmpty.style.display = "none";
      chunksDistribution.style.display = "flex";
      chunksStatsSummary.style.display = "flex";
      chunksMin.textContent = stats.min;
      chunksMax.textContent = stats.max;
      chunksAvg.textContent = stats.avg;
      var maxCount = Math.max.apply(null, stats.distribution.map(function(d) { return d.count; }));
      chunksDistribution.innerHTML = "";
      stats.distribution.forEach(function(item) {
        var pct = maxCount > 0 ? (item.count / maxCount * 100) : 0;
        var row = document.createElement("div");
        row.className = "chunk-bar-row";
        row.innerHTML = '<span class="chunk-bar-label">' + item.range + '</span>' +
          '<div class="chunk-bar-wrap">' +
          '<div class="chunk-bar" style="width:' + pct + '%"></div>' +
          '<span class="chunk-bar-count">' + item.count + '</span>' +
          '</div>';
        chunksDistribution.appendChild(row);
      });
    } catch (err) {
      console.error("loadChunksStats error:", err);
      chunksEmpty.style.display = "block";
      chunksDistribution.style.display = "none";
      chunksStatsSummary.style.display = "none";
    }
  }

  refreshChunksBtn.addEventListener("click", function () {
    loadChunksStats();
    this.style.transform = "rotate(360deg)";
    setTimeout(function () { refreshChunksBtn.style.transform = ""; }, 300);
  });


  /* ========== Init ========== */
  loadDocuments();
  loadHealth();
  loadChunksStats();
  checkActiveJobs();
  pollKbBadge();

  var _kbPollTimer = null;
  function pollKbBadge() {
    if (_kbPollTimer) clearInterval(_kbPollTimer);
    _kbPollTimer = setInterval(function () {
      var badge = document.getElementById("kbIngestBadge");
      if (!badge) { clearInterval(_kbPollTimer); return; }
      fetch("/api/kb/jobs/active").then(function (r) { return r.json(); }).then(function (data) {
        if (!badge) return;
        badge.style.display = (data.ok && data.jobs && data.jobs.length > 0) ? "inline-flex" : "none";
      }).catch(function () {});
    }, 5000);
  }

  async function checkActiveJobs() {
    try {
      var res = await fetch("/api/kb/jobs/active");
      var data = await res.json().catch(function () { return {}; });
      if (data.ok && data.jobs && data.jobs.length > 0) {
        var job = data.jobs[0];
        startProgressPoll(job.job_id, job.source);
        showToast("检测到正在进行的入库任务，已恢复进度", "info");
      }
    } catch (err) {}
  }

})();
