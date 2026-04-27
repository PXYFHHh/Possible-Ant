<template>
  <div class="think-block">
    <button class="think-header" @click="expanded = !expanded">
      <div class="think-header-left">
        <Sparkles :size="14" class="think-icon" />
        <span>思考过程</span>
      </div>
      <div class="think-header-right">
        <span class="think-badge" v-if="typing">思考中...</span>
        <ChevronDown :size="14" class="think-chevron" :class="{ open: expanded }" />
      </div>
    </button>
    <div class="think-body" :class="{ open: expanded }" v-show="expanded">
      <div class="think-content" v-html="rendered" />
      <span v-if="typing" class="cursor-blink">|</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { Sparkles, ChevronDown } from 'lucide-vue-next'
import { renderMarkdown } from '@/utils'

const props = defineProps({
  content: { type: String, default: '' },
  typing: { type: Boolean, default: false },
})

const expanded = ref(true)

const rendered = computed(() => renderMarkdown(props.content || ''))
</script>

<style scoped>
.think-block {
  margin-bottom: 10px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  overflow: hidden;
  background: rgba(99, 102, 241, 0.03);
}

.think-header {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  cursor: pointer;
  transition: all var(--transition-fast);
}
.think-header:hover { background: rgba(99, 102, 241, 0.05); }

.think-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--text-secondary);
}

.think-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.think-icon { color: var(--accent-light); }
.think-icon {
  animation: pulse-breath 2s ease-in-out infinite;
}

.think-badge {
  font-size: 0.6875rem;
  color: var(--accent-light);
  opacity: 0.7;
}

.think-chevron {
  color: var(--text-muted);
  transition: transform var(--transition-fast);
}
.think-chevron.open { transform: rotate(180deg); }

.think-body {
  border-top: 1px solid var(--glass-border);
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.35s ease;
}
.think-body.open { max-height: 400px; overflow-y: auto; }

.think-content {
  padding: 14px;
  font-size: 0.8125rem;
  line-height: 1.65;
  color: var(--text-secondary);
}
.think-content :deep(p) { margin: 0 0 6px; }
.think-content :deep(p:last-child) { margin-bottom: 0; }
.think-content :deep(code) {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  background: rgba(99, 102, 241, 0.08);
  padding: 2px 6px;
  border-radius: 3px;
}

.cursor-blink {
  color: var(--accent-light);
  animation: cursor-blink 1s step-end infinite;
}
</style>
