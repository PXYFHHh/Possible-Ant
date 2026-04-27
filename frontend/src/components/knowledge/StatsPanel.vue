<template>
  <div v-if="stats && stats.total" class="stats-block">
    <div class="stats-summary">
      <span class="stat-item">最小 <em>{{ stats.min }}</em></span>
      <span class="stat-div">·</span>
      <span class="stat-item">最大 <em>{{ stats.max }}</em></span>
      <span class="stat-div">·</span>
      <span class="stat-item">平均 <em>{{ stats.avg }}</em></span>
    </div>
    <div class="bar-list">
      <div v-for="(d, i) in stats.distribution" :key="i" class="bar-row">
        <span class="bar-label">{{ d.range }}</span>
        <div class="bar-track">
          <div class="bar-fill" :style="{ width: barPct(d.count) + '%' }" />
        </div>
        <span class="bar-val">{{ d.count }}</span>
      </div>
    </div>
  </div>
  <div v-else class="empty">
    <BarChart3 :size="28" stroke-width="1" />
    <p>暂无切片数据</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { BarChart3 } from 'lucide-vue-next'

const props = defineProps({
  stats: { type: Object, default: null },
})

function barPct(count) {
  if (!props.stats?.distribution) return 0
  const max = Math.max(...props.stats.distribution.map((d) => d.count), 1)
  return (count / max) * 100
}
</script>

<style scoped>
.stats-summary {
  display: flex;
  gap: 4px;
  margin-bottom: 14px;
  font-size: 0.8125rem;
  color: var(--text-secondary);
}
.stat-item em { font-weight: 600; color: var(--text-primary); font-style: normal; }
.stat-div { color: var(--text-muted); }

.bar-list { display: flex; flex-direction: column; gap: 5px; }

.bar-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.bar-label {
  width: 42px;
  font-size: 0.625rem;
  color: var(--text-muted);
  text-align: right;
  flex-shrink: 0;
  font-family: var(--font-mono);
}

.bar-track {
  flex: 1;
  height: 16px;
  background: var(--bg-input);
  border-radius: 3px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  border-radius: 3px;
  background: linear-gradient(90deg, var(--accent), var(--accent-2));
  transition: width 0.6s ease;
}

.bar-val {
  width: 32px;
  font-size: 0.625rem;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px;
  color: var(--text-muted);
  font-size: 0.8125rem;
}
</style>
