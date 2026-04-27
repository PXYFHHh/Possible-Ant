<template>
  <div class="doc-row" v-for="doc in docs" :key="doc.source">
    <div class="doc-icon" :class="iconClass(doc.source)">
      <FileText :size="18" />
    </div>
    <div class="doc-body">
      <div class="doc-name">{{ doc.source }}</div>
      <div class="doc-meta">
        <span>{{ doc.chunk_count ?? 0 }} chunks</span>
        <span>{{ formatTimeShort(doc.updated_at) }}</span>
      </div>
    </div>
    <button class="doc-del" @click="$emit('delete', doc.source)" title="删除">
      <Trash2 :size="14" />
    </button>
  </div>
</template>

<script setup>
import { FileText, Trash2 } from 'lucide-vue-next'
import { formatTimeShort } from '@/utils'

defineProps({
  docs: { type: Array, default: () => [] },
})

defineEmits(['delete'])

function iconClass(name) {
  const ext = (name || '').split('.').pop().toLowerCase()
  const map = { pdf: 'ic-pdf', docx: 'ic-docx', md: 'ic-md', markdown: 'ic-md', txt: 'ic-txt' }
  return map[ext] || 'ic-txt'
}
</script>

<style scoped>
.doc-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: var(--radius-md);
  transition: all var(--transition-fast);
}
.doc-row:hover { background: rgba(99, 102, 241, 0.04); }

.doc-icon {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.ic-pdf { background: rgba(239, 68, 68, 0.12); color: var(--danger); }
.ic-docx { background: rgba(99, 102, 241, 0.12); color: var(--accent-light); }
.ic-md { background: rgba(16, 185, 129, 0.12); color: var(--success); }
.ic-txt { background: var(--bg-input); color: var(--text-muted); }

.doc-body { flex: 1; min-width: 0; }
.doc-name {
  font-size: 0.875rem;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.doc-meta {
  font-size: 0.71875rem;
  color: var(--text-muted);
  margin-top: 2px;
  display: flex;
  gap: 12px;
}

.doc-del {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  opacity: 0;
  transition: all var(--transition-fast);
}
.doc-row:hover .doc-del { opacity: 1; }
.doc-del:hover { color: var(--danger); background: rgba(239, 68, 68, 0.1); }
</style>
