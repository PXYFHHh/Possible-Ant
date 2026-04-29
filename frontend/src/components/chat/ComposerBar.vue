<template>
  <div class="composer-bar glass">
    <div class="composer-toolbar">
      <button
        class="toggle-btn"
        :class="{ on: ragEnabled }"
        :disabled="generating"
        @click="$emit('toggle-rag')"
        :title="ragEnabled ? '知识库检索已开启' : '知识库检索已关闭'"
      >
        <BookOpen :size="15" />
        <span>知识库</span>
      </button>
      <button
        class="toggle-btn"
        :class="{ on: webSearchEnabled }"
        :disabled="generating"
        @click="$emit('toggle-web')"
        :title="webSearchEnabled ? '联网搜索已开启' : '联网搜索已关闭'"
      >
        <Globe :size="15" />
        <span>联网</span>
      </button>
    </div>
    <div class="composer-main">
      <textarea
        ref="inputEl"
        v-model="text"
        :placeholder="generating ? '正在生成回复...' : '输入问题，Enter 发送，Shift+Enter 换行'"
        :disabled="generating"
        rows="1"
        class="composer-input"
        @keydown="handleKeydown"
        @input="autoResize"
      />
      <button
        class="composer-send"
        :class="{ stop: generating }"
        :disabled="!generating && !text.trim()"
        @click="handleClick"
        :title="generating ? '停止' : '发送'"
      >
        <Send v-if="!generating" :size="18" />
        <Square v-else :size="16" />
      </button>
    </div>
    <div class="composer-hint" v-if="!generating && !text.trim()">
      <kbd>Enter</kbd> 发送 · <kbd>Shift + Enter</kbd> 换行 · <kbd>/</kbd> 聚焦
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import { Send, Square, BookOpen, Globe } from 'lucide-vue-next'

const props = defineProps({
  generating: { type: Boolean, default: false },
  ragEnabled: { type: Boolean, default: true },
  webSearchEnabled: { type: Boolean, default: true },
})

const emit = defineEmits(['send', 'stop', 'toggle-rag', 'toggle-web'])

const text = ref('')
const inputEl = ref(null)

function autoResize() {
  const el = inputEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 160) + 'px'
}

function handleClick() {
  if (props.generating) {
    emit('stop')
  } else if (text.value.trim()) {
    emit('send', text.value.trim())
    text.value = ''
    nextTick(() => {
      if (inputEl.value) {
        inputEl.value.style.height = 'auto'
        inputEl.value.focus()
      }
    })
  }
}

function handleKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleClick()
  }
}

function focus() {
  inputEl.value?.focus()
}

defineExpose({ focus })
</script>

<style scoped>
.composer-bar {
  padding: 5px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--glass-border);
  transition: all var(--transition-fast);
}

.composer-bar:focus-within {
  border-color: var(--glass-border-hover);
  box-shadow: 0 0 0 3px var(--accent-glow);
}

.composer-toolbar {
  display: flex;
  gap: 6px;
  padding: 4px 8px 2px;
}

.toggle-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: var(--radius-full);
  border: 1px solid var(--glass-border);
  background: transparent;
  color: var(--text-muted);
  font-size: 0.75rem;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.toggle-btn:hover:not(:disabled) {
  border-color: var(--glass-border-hover);
  color: var(--text-secondary);
}

.toggle-btn.on {
  background: rgba(99, 102, 241, 0.12);
  border-color: var(--accent);
  color: var(--accent-light);
}

.toggle-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.toggle-btn span { font-weight: 500; }

.composer-main {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 4px 8px 6px 14px;
}

.composer-input {
  flex: 1;
  border: none;
  background: transparent;
  resize: none;
  outline: none;
  font-size: 0.9375rem;
  line-height: 1.6;
  color: var(--text-primary);
  padding: 6px 0;
  max-height: 160px;
}

.composer-input::placeholder { color: var(--text-muted); }
.composer-input:disabled { opacity: 0.5; }

.composer-send {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
  color: #fff;
  flex-shrink: 0;
  transition: all var(--transition-fast);
  box-shadow: 0 4px 12px var(--accent-glow);
}

.composer-send:hover:not(:disabled) {
  transform: scale(1.05) rotate(15deg);
  box-shadow: 0 6px 20px var(--accent-glow);
}

.composer-send:active:not(:disabled) { transform: scale(0.95); }

.composer-send:disabled { opacity: 0.35; cursor: not-allowed; }

.composer-send.stop {
  background: linear-gradient(135deg, var(--danger), #f87171);
  box-shadow: 0 4px 12px var(--danger-glow);
  animation: pulse-glow 2s ease-in-out infinite;
}

.composer-hint {
  text-align: center;
  padding: 2px 0 8px;
  font-size: 0.6875rem;
  color: var(--text-muted);
  opacity: 0.6;
}

.composer-hint kbd {
  display: inline-block;
  padding: 1px 6px;
  background: rgba(99, 102, 241, 0.1);
  border: 1px solid var(--glass-border);
  border-radius: 3px;
  font-family: var(--font-mono);
  font-size: 0.625rem;
  color: var(--text-secondary);
}
</style>
