<template>
  <div class="msg-card" :class="role">
    <div class="msg-inner">
      <div class="msg-content" v-html="rendered" />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { renderMarkdown } from '@/utils'

const props = defineProps({
  text: { type: String, required: true },
  role: { type: String, default: 'user' },
})

const rendered = computed(() => {
  if (props.role === 'user') return props.text.replace(/\n/g, '<br>')
  return renderMarkdown(props.text)
})
</script>

<style scoped>
.msg-card {
  display: flex;
  margin-bottom: 20px;
  animation: fadeInUp 0.35s ease-out both;
}

.msg-card.user { justify-content: flex-end; }

.msg-inner {
  max-width: 72%;
}

.msg-card.user .msg-inner {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.2), rgba(139, 92, 246, 0.15));
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: var(--radius-lg) 4px var(--radius-lg) var(--radius-lg);
}

.msg-card.assistant .msg-inner {
  background: var(--bg-card);
  border: 1px solid var(--glass-border);
  border-radius: 4px var(--radius-lg) var(--radius-lg) var(--radius-lg);
}

.msg-content {
  padding: 14px 18px;
  font-size: 0.9375rem;
  line-height: 1.7;
  word-break: break-word;
}

.msg-card.user .msg-content { color: var(--text-primary); }
.msg-card.assistant .msg-content { color: #d4d8e3; }

.msg-content :deep(p) { margin: 0 0 8px; }
.msg-content :deep(p:last-child) { margin-bottom: 0; }
.msg-content :deep(pre) {
  background: var(--bg-code);
  border-radius: var(--radius-sm);
  padding: 14px;
  font-size: 0.8125rem;
  font-family: var(--font-mono);
  overflow-x: auto;
  margin: 10px 0;
  border: 1px solid var(--glass-border);
}
.msg-content :deep(code) {
  font-family: var(--font-mono);
  font-size: 0.8125rem;
  background: rgba(99, 102, 241, 0.1);
  padding: 2px 6px;
  border-radius: 3px;
}
.msg-content :deep(pre code) { background: none; padding: 0; }
.msg-content :deep(ul), .msg-content :deep(ol) { padding-left: 20px; margin: 6px 0; }
.msg-content :deep(blockquote) {
  border-left: 2px solid var(--accent);
  padding: 6px 14px;
  margin: 10px 0;
  color: var(--text-secondary);
  background: rgba(99, 102, 241, 0.04);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
}
.msg-content :deep(a) { color: var(--accent-light); text-decoration: underline; }
.msg-content :deep(strong) { color: var(--text-primary); font-weight: 600; }
</style>
