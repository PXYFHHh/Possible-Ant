<template>
  <div class="glass-panel" :class="[`depth-${depth}`]">
    <slot />
  </div>
</template>

<script setup>
defineProps({
  depth: { type: Number, default: 1 },
})
</script>

<style scoped>
.glass-panel {
  background: var(--bg-surface);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-radius: var(--radius-lg);
  border: 1px solid var(--glass-border);
  overflow: hidden;
}
.glass-panel.depth-2 {
  background: var(--bg-card);
  backdrop-filter: blur(16px);
}
.glass-panel.depth-3 {
  background: var(--bg-input);
  backdrop-filter: blur(12px);
}
</style>
