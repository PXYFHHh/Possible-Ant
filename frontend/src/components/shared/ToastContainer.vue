<template>
  <Teleport to="body">
    <div class="toast-container">
      <TransitionGroup name="toast">
        <div
          v-for="t in toasts"
          :key="t.id"
          class="toast"
          :class="t.type"
          @click="dismiss(t.id)"
        >
          <span class="toast-dot" />
          <span class="toast-msg">{{ t.message }}</span>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup>
import { ref } from 'vue'

const toasts = ref([])
let idCounter = 0

function show(message, type = 'info') {
  const id = ++idCounter
  toasts.value.push({ id, message, type })
  setTimeout(() => dismiss(id), 3500)
}

function dismiss(id) {
  const idx = toasts.value.findIndex((t) => t.id === id)
  if (idx >= 0) toasts.value.splice(idx, 1)
  if (toasts.value.length > 4) toasts.value.shift()
}

defineExpose({ show })
</script>

<style scoped>
.toast-container {
  position: fixed;
  top: 20px;
  right: 20px;
  z-index: 10000;
  display: flex;
  flex-direction: column;
  gap: 8px;
  pointer-events: none;
}

.toast {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 18px;
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  backdrop-filter: blur(20px);
  border: 1px solid var(--glass-border);
  box-shadow: var(--glass-shadow);
  font-size: 0.875rem;
  color: var(--text-primary);
  cursor: pointer;
  pointer-events: all;
  max-width: 360px;
}

.toast-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.toast.info .toast-dot { background: var(--accent); }
.toast.success .toast-dot { background: var(--success); box-shadow: 0 0 8px var(--success-glow); }
.toast.error .toast-dot { background: var(--danger); box-shadow: 0 0 8px var(--danger-glow); }
.toast.warning .toast-dot { background: var(--warning); }

.toast-enter-active { transition: all 0.35s cubic-bezier(0.34, 1.56, 0.64, 1); }
.toast-leave-active { transition: all 0.2s ease-in; }
.toast-enter-from { opacity: 0; transform: translateX(40px) scale(0.9); }
.toast-leave-to { opacity: 0; transform: translateX(40px) scale(0.9); }
</style>
