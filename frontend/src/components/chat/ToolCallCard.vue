<template>
  <div class="tool-card">
    <button class="tool-head" @click="expanded = !expanded">
      <div class="tool-head-left">
        <Wrench :size="14" />
        <span class="tool-name">{{ name }}</span>
        <span v-if="!done" class="tool-status running">执行中</span>
        <span v-else class="tool-status done">完成</span>
      </div>
      <ChevronDown :size="14" class="tool-chevron" :class="{ open: expanded }" />
    </button>
    <div class="tool-body" :class="{ open: expanded }" v-show="expanded">
      <div class="tool-section">
        <div class="tool-label">参数</div>
        <pre class="tool-pre">{{ JSON.stringify(args, null, 2) }}</pre>
      </div>
      <div class="tool-section" v-if="result">
        <div class="tool-label">结果</div>
        <div v-if="isRagResult(result)" class="rag-chunks">
          <div v-for="(chunk, ci) in ragChunks" :key="ci" class="rag-chunk" @click="$emit('open-chunk', { chunk, index: ci, all: ragChunks })">
            <span class="rag-chunk-idx">{{ chunk.index }}</span>
            <span class="rag-chunk-src">{{ chunk.source }}</span>
            <span class="rag-chunk-score">hybrid: {{ chunk.hybrid.toFixed(4) }}</span>
          </div>
        </div>
        <pre v-else class="tool-pre">{{ result.slice(0, 3000) }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Wrench, ChevronDown } from 'lucide-vue-next'
import { isRagResult, parseRagResult } from '@/utils'

const props = defineProps({
  name: { type: String, default: 'tool' },
  args: { type: Object, default: () => ({}) },
  result: { type: String, default: '' },
  done: { type: Boolean, default: false },
})

defineEmits(['open-chunk'])

const expanded = ref(true)

const ragChunks = computed(() => {
  if (!props.result || !isRagResult(props.result)) return []
  return parseRagResult(props.result).chunks
})
</script>

<style scoped>
.tool-card {
  margin-bottom: 10px;
  border: 1px solid rgba(245, 158, 11, 0.15);
  border-radius: var(--radius-md);
  overflow: hidden;
  background: rgba(245, 158, 11, 0.03);
}

.tool-head {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  cursor: pointer;
  transition: all var(--transition-fast);
  color: var(--text-secondary);
}
.tool-head:hover { background: rgba(245, 158, 11, 0.05); }

.tool-head-left {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.8125rem;
}

.tool-name {
  font-weight: 500;
  color: #fbbf24;
  font-family: var(--font-mono);
}

.tool-status {
  font-size: 0.6875rem;
  padding: 2px 7px;
  border-radius: var(--radius-full);
  font-weight: 500;
}
.tool-status.running {
  background: rgba(245, 158, 11, 0.15);
  color: #fbbf24;
  animation: pulse-breath 1.5s ease-in-out infinite;
}
.tool-status.done {
  background: rgba(16, 185, 129, 0.12);
  color: var(--success);
}

.tool-chevron {
  color: var(--text-muted);
  transition: transform var(--transition-fast);
}
.tool-chevron.open { transform: rotate(180deg); }

.tool-body {
  border-top: 1px solid rgba(245, 158, 11, 0.1);
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.35s ease;
}
.tool-body.open { max-height: 500px; overflow-y: auto; }

.tool-section { padding: 10px 14px; }
.tool-section + .tool-section { border-top: 1px dashed rgba(245, 158, 11, 0.08); }

.tool-label {
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  margin-bottom: 6px;
}

.tool-pre {
  font-family: var(--font-mono);
  font-size: 0.71875rem;
  line-height: 1.5;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  background: rgba(0, 0, 0, 0.15);
  border-radius: var(--radius-sm);
  padding: 10px;
}

.rag-chunks {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.rag-chunk {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  background: rgba(99, 102, 241, 0.06);
  border: 1px solid transparent;
  cursor: pointer;
  transition: all var(--transition-fast);
}
.rag-chunk:hover { border-color: var(--glass-border-hover); background: rgba(99, 102, 241, 0.1); }

.rag-chunk-idx {
  width: 20px;
  height: 20px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: rgba(99, 102, 241, 0.15);
  color: var(--accent-light);
  font-size: 0.6875rem;
  font-weight: 700;
  flex-shrink: 0;
}

.rag-chunk-src {
  flex: 1;
  font-size: 0.75rem;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rag-chunk-score {
  font-size: 0.6875rem;
  font-family: var(--font-mono);
  color: var(--text-muted);
}
</style>
