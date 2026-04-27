<template>
  <Transition name="panel">
    <div v-if="visible" class="panel-overlay" @click.self="$emit('close')">
      <div class="panel" @click.stop>
        <div class="panel-head">
          <h2 class="panel-title">对话</h2>
          <div class="panel-actions">
            <button class="panel-btn" @click="store.enterBatchMode()" v-if="!store.batchMode" title="批量管理">
              <CheckSquare :size="16" />
            </button>
            <button class="panel-btn" @click="$emit('close')" title="关闭">
              <X :size="16" />
            </button>
          </div>
        </div>

        <div class="panel-search">
          <Search :size="14" class="search-icon" />
          <input
            v-model="store.searchQuery"
            type="text"
            placeholder="搜索对话..."
            class="search-input"
          />
        </div>

        <div class="panel-list" v-if="store.filteredConversations.length">
          <div
            v-for="(conv, i) in store.filteredConversations"
            :key="conv.id"
            class="conv-row"
            :class="{
              active: conv.id === store.activeId,
              'batch-selected': store.batchMode && store.batchSelected.has(conv.id),
            }"
            :style="{ animationDelay: `${i * 30}ms` }"
            @click="handleClick(conv)"
          >
            <div v-if="store.batchMode" class="batch-dot" :class="{ on: store.batchSelected.has(conv.id) }" />
            <div class="conv-info">
              <div class="conv-name">{{ conv.title || '新对话' }}</div>
              <div class="conv-sub">{{ (conv.messages?.length || 0) }} 条 · {{ formatTime(conv.updatedAt) }}</div>
            </div>
            <button
              v-if="!store.batchMode"
              class="conv-del"
              @click.stop="$emit('delete', conv.id)"
              title="删除"
            >
              <Trash2 :size="14" />
            </button>
          </div>
        </div>

        <div v-else class="panel-empty">
          <MessageCircle :size="32" stroke-width="1" />
          <p>{{ store.searchQuery ? '没有匹配的对话' : '暂无历史对话' }}</p>
        </div>

        <div v-if="store.batchMode" class="panel-batch-bar">
          <span>已选 <em>{{ store.batchSelected.size }}</em> 项</span>
          <div class="batch-btns">
            <button class="btn-batch" @click="store.selectAllBatch()">全选</button>
            <button class="btn-batch danger" :disabled="!store.batchSelected.size" @click="$emit('batch-delete')">删除选中</button>
            <button class="btn-batch" @click="store.exitBatchMode()">取消</button>
          </div>
        </div>

        <div class="panel-foot">
          <button class="btn-new" @click="$emit('new')">
            <Plus :size="16" /> 新建对话
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { MessageCircle, Search, Plus, X, Trash2, CheckSquare } from 'lucide-vue-next'
import { useChatStore } from '@/stores/chat'
import { formatTime } from '@/utils'

defineProps({
  visible: { type: Boolean, default: false },
})

const emit = defineEmits(['close', 'new', 'delete', 'batch-delete'])
const store = useChatStore()

function handleClick(conv) {
  if (store.batchMode) {
    store.toggleBatchSelect(conv.id)
  } else {
    store.switchConversation(conv.id)
    emit('close')
  }
}
</script>

<style scoped>
.panel-overlay {
  position: fixed;
  inset: 0;
  z-index: 500;
  display: flex;
  background: rgba(5, 7, 14, 0.7);
  backdrop-filter: blur(8px);
}

.panel {
  width: 340px;
  max-width: 90vw;
  height: 100vh;
  background: var(--bg-surface);
  backdrop-filter: blur(24px);
  border-right: 1px solid var(--glass-border);
  display: flex;
  flex-direction: column;
  box-shadow: 8px 0 32px rgba(0, 0, 0, 0.4);
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 20px 12px;
}

.panel-title {
  font-family: var(--font-display);
  font-size: 1.125rem;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.panel-actions {
  display: flex;
  gap: 4px;
}

.panel-btn {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  transition: all var(--transition-fast);
}
.panel-btn:hover { color: var(--text-primary); background: rgba(99, 102, 241, 0.1); }

.panel-search {
  position: relative;
  margin: 0 16px 12px;
}

.search-icon {
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-muted);
  pointer-events: none;
}

.search-input {
  width: 100%;
  padding: 10px 12px 10px 34px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  background: var(--bg-input);
  color: var(--text-primary);
  font-size: 0.8125rem;
  outline: none;
  transition: all var(--transition-fast);
}
.search-input::placeholder { color: var(--text-muted); }
.search-input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }

.panel-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 12px;
}

.conv-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);
  margin-bottom: 2px;
  animation: fadeInUp 0.3s ease-out both;
  position: relative;
}

.conv-row::after {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 2px;
  height: 0;
  background: linear-gradient(to bottom, var(--accent), var(--accent-2));
  border-radius: 1px;
  transition: height var(--transition-fast);
}

.conv-row:hover { background: rgba(99, 102, 241, 0.06); }
.conv-row.active { background: rgba(99, 102, 241, 0.1); }
.conv-row.active::after { height: 24px; }
.conv-row.batch-selected { background: rgba(99, 102, 241, 0.12); }

.batch-dot {
  width: 18px;
  height: 18px;
  border: 2px solid var(--glass-border);
  border-radius: 4px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  transition: all var(--transition-fast);
}
.batch-dot.on {
  background: var(--accent);
  border-color: var(--accent);
}
.batch-dot.on::after {
  content: '';
  width: 8px;
  height: 4px;
  border-left: 2px solid #fff;
  border-bottom: 2px solid #fff;
  transform: rotate(-45deg) translate(1px, -1px);
}

.conv-info { flex: 1; min-width: 0; }
.conv-name {
  font-size: 0.875rem;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.conv-sub { font-size: 0.71875rem; color: var(--text-muted); margin-top: 1px; }

.conv-del {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  opacity: 0;
  transition: all var(--transition-fast);
}
.conv-row:hover .conv-del { opacity: 1; }
.conv-del:hover { color: var(--danger); background: rgba(239, 68, 68, 0.1); }

.panel-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--text-muted);
  font-size: 0.875rem;
  padding: 32px;
}

.panel-batch-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  margin: 0 12px 8px;
  background: rgba(99, 102, 241, 0.08);
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border);
  font-size: 0.8125rem;
  color: var(--text-secondary);
}
.panel-batch-bar em { color: var(--accent-light); font-style: normal; font-weight: 600; }
.batch-btns { display: flex; gap: 6px; }

.btn-batch {
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.75rem;
  cursor: pointer;
  transition: all var(--transition-fast);
}
.btn-batch:hover { border-color: var(--glass-border-hover); color: var(--text-primary); }
.btn-batch.danger:not(:disabled):hover { border-color: rgba(239, 68, 68, 0.3); color: var(--danger); }
.btn-batch:disabled { opacity: 0.4; cursor: not-allowed; }

.panel-foot {
  padding: 14px 16px 20px;
}

.btn-new {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px;
  border-radius: var(--radius-md);
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
  color: #fff;
  font-weight: 600;
  font-size: 0.875rem;
  cursor: pointer;
  transition: all var(--transition-fast);
  box-shadow: 0 4px 16px var(--accent-glow);
}
.btn-new:hover { transform: translateY(-1px); box-shadow: 0 6px 24px var(--accent-glow); }
.btn-new:active { transform: translateY(0); }

.panel-enter-active { transition: all 0.3s ease-out; }
.panel-leave-active { transition: all 0.2s ease-in; }
.panel-enter-from,
.panel-leave-to { opacity: 0; }
.panel-enter-from .panel { transform: translateX(-20px); }
.panel-enter-to .panel,
.panel-leave-from .panel { transform: translateX(0); }
.panel-leave-to .panel { transform: translateX(-20px); }
</style>
