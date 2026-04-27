<template>
  <div class="dropzone" :class="{ dragover: isOver, hasfile: file }" @click="openPicker">
    <input ref="inputEl" type="file" accept=".txt,.md,.markdown,.pdf,.docx" hidden @change="onFileChange" />
    <div
      @dragover.prevent="isOver = true"
      @dragleave.prevent="isOver = false"
      @drop.prevent="onDrop"
    >
      <div v-if="!file" class="dz-empty">
        <Upload :size="32" stroke-width="1.5" class="dz-icon" />
        <p class="dz-text">拖拽文件到此处，或<span class="dz-link">点击选择</span></p>
        <p class="dz-hint">支持 txt / md / pdf / docx，不超过 50MB</p>
      </div>
      <div v-else class="dz-file">
        <FileText :size="18" />
        <span class="dz-filename">{{ file.name }}</span>
        <span class="dz-filesize">{{ formatFileSize(file.size) }}</span>
        <button class="dz-clear" @click.stop="clear">&times;</button>
      </div>
    </div>
  </div>

  <div class="upload-actions">
    <button class="btn-primary" :disabled="!file || uploading" @click="$emit('upload', file)">
      <Upload :size="16" />
      {{ uploading ? '入库中...' : '上传并入库' }}
    </button>
    <button v-if="file" class="btn-ghost" @click="clear">取消</button>
  </div>

  <div v-if="progress" class="progress-block">
    <div class="progress-bar-wrap">
      <div class="progress-bar" :style="{ width: progress.pct + '%' }" />
    </div>
    <div class="progress-info">
      <template v-if="progress.total">
        切片进度: {{ progress.done }} / {{ progress.total }} ({{ progress.pct }}%)
      </template>
      <template v-else>切片中...</template>
    </div>
  </div>

  <div v-if="result" class="result" :class="result.type">
    {{ result.message }}
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Upload, FileText } from 'lucide-vue-next'
import { formatFileSize } from '@/utils'

const props = defineProps({
  uploading: Boolean,
  progress: Object,
  result: Object,
})

const emit = defineEmits(['upload', 'select'])

const inputEl = ref(null)
const file = ref(null)
const isOver = ref(false)

function openPicker() {
  inputEl.value?.click()
}

function selectFile(f) {
  if (!f) return
  if (f.size > 50 * 1024 * 1024) {
    emit('select', null)
    return
  }
  file.value = f
}

function onFileChange(e) {
  selectFile(e.target.files?.[0])
}

function onDrop(e) {
  isOver.value = false
  selectFile(e.dataTransfer?.files?.[0])
}

function clear() {
  file.value = null
  if (inputEl.value) inputEl.value.value = ''
}
</script>

<style scoped>
.dropzone {
  border: 2px dashed var(--glass-border);
  border-radius: var(--radius-lg);
  padding: 32px 24px;
  text-align: center;
  cursor: pointer;
  transition: all var(--transition-fast);
  margin-bottom: 14px;
}
.dropzone:hover { border-color: var(--glass-border-hover); background: rgba(99, 102, 241, 0.03); }
.dropzone.dragover {
  border-color: var(--accent);
  border-style: solid;
  background: rgba(99, 102, 241, 0.06);
  box-shadow: 0 0 24px var(--accent-glow);
}
.dropzone.hasfile { border-style: solid; border-color: var(--glass-border-hover); }

.dz-empty { color: var(--text-muted); }
.dz-icon { margin-bottom: 12px; opacity: 0.5; }
.dz-text { font-size: 0.9375rem; margin-bottom: 6px; }
.dz-link { color: var(--accent-light); }
.dz-hint { font-size: 0.75rem; opacity: 0.6; }

.dz-file {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--text-primary);
  font-size: 0.9375rem;
}
.dz-filesize { font-size: 0.75rem; color: var(--text-muted); }
.dz-clear {
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  color: var(--text-muted);
  font-size: 1.125rem;
  transition: all var(--transition-fast);
}
.dz-clear:hover { background: rgba(239, 68, 68, 0.1); color: var(--danger); }

.upload-actions { display: flex; gap: 8px; justify-content: center; margin-bottom: 14px; }

.progress-block { margin-bottom: 14px; }

.progress-bar-wrap {
  height: 6px;
  background: var(--bg-input);
  border-radius: 3px;
  overflow: hidden;
  margin-bottom: 8px;
}

.progress-bar {
  height: 100%;
  background: linear-gradient(90deg, var(--accent), var(--accent-2));
  border-radius: 3px;
  transition: width 0.4s ease;
}

.progress-info {
  text-align: center;
  font-size: 0.75rem;
  color: var(--text-muted);
}

.result {
  padding: 12px 16px;
  border-radius: var(--radius-md);
  font-size: 0.875rem;
  text-align: center;
  margin-bottom: 14px;
}
.result.success { background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.2); color: var(--success); }
.result.error { background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.2); color: var(--danger); }
</style>
