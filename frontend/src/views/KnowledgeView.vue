<template>
  <div class="kb-canvas">
    <header class="kb-topbar">
      <div class="kb-topbar-left">
        <BookOpen :size="18" />
        <span class="kb-topbar-title">知识库管理</span>
      </div>
      <span v-if="store.activeJobs.length" class="kb-active-badge">
        <span class="kb-active-dot" />
        {{ store.activeJobs.length }} 个入库任务
      </span>
    </header>

    <div class="kb-body">
      <div class="kb-grid">
        <section class="kb-card glass-card anim-fade-in-up">
          <div class="kb-card-head">
            <Upload :size="18" />
            <span>文档入库</span>
          </div>
          <UploadDropzone
            :uploading="store.uploading"
            :progress="store.uploadProgress"
            :result="store.uploadResult"
            @upload="handleUpload"
          />
        </section>

        <section class="kb-card glass-card anim-fade-in-up stagger-1">
          <div class="kb-card-head">
            <FileText :size="18" />
            <span>已入库文档</span>
            <span class="kb-badge">{{ store.documents.length }}</span>
            <button class="kb-refresh" @click="store.loadDocuments()" title="刷新">
              <RefreshCw :size="14" />
            </button>
          </div>
          <div v-if="store.loading" class="kb-loading">加载中...</div>
          <div v-else-if="!store.documents.length" class="kb-empty">
            <FileText :size="28" stroke-width="1" />
            <p>暂无文档</p>
          </div>
          <DocCard v-else :docs="store.documents" @delete="handleDelete" />
        </section>

        <section class="kb-card glass-card anim-fade-in-up stagger-2">
          <div class="kb-card-head">
            <BarChart3 :size="18" />
            <span>切片分布</span>
            <span class="kb-badge" v-if="store.chunksStats?.total">{{ store.chunksStats.total }}</span>
            <button class="kb-refresh" @click="store.loadChunkStats()" title="刷新">
              <RefreshCw :size="14" />
            </button>
          </div>
          <StatsPanel :stats="store.chunksStats" />
        </section>

        <section class="kb-card glass-card anim-fade-in-up stagger-3">
          <div class="kb-card-head">
            <Activity :size="18" />
            <span>RAG 健康</span>
            <button class="kb-refresh" @click="store.loadHealth()" title="刷新">
              <RefreshCw :size="14" />
            </button>
          </div>
          <div v-if="!store.healthData" class="kb-loading">加载中...</div>
          <pre v-else class="kb-health">{{ JSON.stringify(store.healthData, null, 2) }}</pre>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { BookOpen, Upload, FileText, BarChart3, Activity, RefreshCw } from 'lucide-vue-next'
import { useKbStore } from '@/stores/knowledge'
import UploadDropzone from '@/components/knowledge/UploadDropzone.vue'
import DocCard from '@/components/knowledge/DocCard.vue'
import StatsPanel from '@/components/knowledge/StatsPanel.vue'

const store = useKbStore()

async function handleUpload(file) {
  const jobId = await store.uploadDocument(file)
  if (jobId) {
    pollLoop(jobId)
  } else {
    refreshAll()
  }
}

async function pollLoop(jobId) {
  const status = await store.pollJob(jobId)
  if (status === 'processing') {
    setTimeout(() => pollLoop(jobId), 1500)
  } else {
    refreshAll()
  }
}

async function handleDelete(source) {
  await store.deleteDocument(source)
  refreshAll()
}

async function refreshAll() {
  await Promise.all([
    store.loadDocuments(),
    store.loadHealth(),
    store.loadChunkStats(),
  ])
}

onMounted(refreshAll)
</script>

<style scoped>
.kb-canvas {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  max-width: 960px;
  margin: 0 auto;
}

.kb-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 24px;
  flex-shrink: 0;
  border-bottom: 1px solid var(--glass-border);
}

.kb-topbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-primary);
}

.kb-topbar-title {
  font-family: var(--font-display);
  font-size: 1rem;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.kb-active-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.75rem;
  color: var(--accent-light);
}
.kb-active-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent-light);
  animation: pulse-breath 1.5s ease-in-out infinite;
}

.kb-body {
  flex: 1;
  overflow-y: auto;
  padding: 28px 24px 48px;
}

.kb-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  align-items: start;
}

@media (max-width: 700px) {
  .kb-grid { grid-template-columns: 1fr; }
}

.kb-card {
  padding: 20px;
}

.kb-card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--text-primary);
}
.kb-card-head svg { color: var(--accent-light); }

.kb-badge {
  font-size: 0.6875rem;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  background: rgba(99, 102, 241, 0.12);
  color: var(--accent-light);
  font-weight: 500;
}

.kb-refresh {
  margin-left: auto;
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  transition: all var(--transition-fast);
}
.kb-refresh:hover { color: var(--text-primary); background: rgba(99, 102, 241, 0.08); }

.kb-loading { color: var(--text-muted); font-size: 0.875rem; padding: 16px 0; }
.kb-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px;
  color: var(--text-muted);
  font-size: 0.8125rem;
}

.kb-health {
  font-family: var(--font-mono);
  font-size: 0.6875rem;
  line-height: 1.6;
  color: var(--text-secondary);
  background: var(--bg-code);
  border-radius: var(--radius-sm);
  padding: 12px;
  max-height: 280px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
