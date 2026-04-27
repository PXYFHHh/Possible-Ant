<template>
  <div class="chat-canvas">
    <header class="canvas-topbar">
      <button class="topbar-btn" @click="panelVisible = true" title="对话列表">
        <Menu :size="18" />
      </button>
      <div class="topbar-center">
        <span class="topbar-title">{{ store.activeConversation?.title || '聊天' }}</span>
      </div>
      <button class="topbar-btn" @click="handleResetMemory" title="清空记忆">
        <RotateCcw :size="16" />
      </button>
    </header>

    <ConversationPanel
      :visible="panelVisible"
      @close="panelVisible = false"
      @new="handleNewConversation"
      @delete="handleDeleteConversation"
      @batch-delete="handleBatchDelete"
    />

    <div class="canvas-body" ref="bodyEl">
      <div class="canvas-messages">
        <Transition name="welcome" mode="out-in">
          <div v-if="!store.messages.length && !store.generating" key="welcome" class="welcome-center">
            <div class="welcome-icon">A</div>
            <h1 class="welcome-heading">有什么可以帮你的？</h1>
            <p class="welcome-desc">
              我是你的本地 AI Agent 助手，支持多轮对话、工具调用和知识库检索。
            </p>
            <div class="welcome-chips">
              <button
                v-for="q in suggestions"
                :key="q"
                class="welcome-chip"
                @click="store.sendMessage(q)"
              >{{ q }}</button>
            </div>
          </div>

          <div v-else key="messages" class="messages-flow">
            <template v-for="(msg, idx) in store.messages" :key="idx">
              <MessageCard
                v-if="msg.role === 'user'"
                :text="msg.content"
                role="user"
              />
              <AssistantBlock
                v-else-if="msg.role === 'assistant'"
                :entry="store.getDisplayEntry(msg)"
                :typing-rounds="store.liveTypingRounds"
                @open-chunk="handleOpenChunk"
              />
            </template>
          </div>
        </Transition>
      </div>
    </div>

    <div class="canvas-footer">
      <div class="composer-wrap">
        <ComposerBar
          ref="composerRef"
          :generating="store.generating"
          @send="store.sendMessage($event)"
          @stop="store.stopMessage()"
        />
      </div>
    </div>

    <Transition name="modal">
      <div v-if="overlayVisible" class="rag-modal-overlay" @click.self="overlayVisible = false">
        <div class="rag-modal glass-card">
          <div class="rag-modal-head">
            <span class="rag-modal-title">{{ overlayCurrent?.source || '片段详情' }}</span>
            <span class="rag-modal-idx">{{ overlayIndex + 1 }} / {{ overlayItems.length }}</span>
            <button class="rag-modal-close" @click="overlayVisible = false">
              <X :size="18" />
            </button>
          </div>
          <div class="rag-modal-tags">
            <span v-if="overlayCurrent?.source" class="rag-tag">{{ overlayCurrent.source }}</span>
            <span v-if="overlayCurrent?.chunkId" class="rag-tag">chunk: {{ overlayCurrent.chunkId }}</span>
            <span v-if="overlayCurrent?.hybrid != null" class="rag-tag score">hybrid: {{ overlayCurrent.hybrid.toFixed(4) }}</span>
          </div>
          <div class="rag-modal-text">{{ overlayCurrent?.text || '（无内容）' }}</div>
          <div class="rag-modal-nav">
            <button class="rag-nav-btn" :disabled="overlayIndex <= 0" @click="overlayIndex--">
              <ChevronLeft :size="16" /> 上一个
            </button>
            <button class="rag-nav-btn" :disabled="overlayIndex >= overlayItems.length - 1" @click="overlayIndex++">
              下一个 <ChevronRight :size="16" />
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { Menu, RotateCcw, X, ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { useChatStore } from '@/stores/chat'
import ConversationPanel from '@/components/chat/ConversationPanel.vue'
import MessageCard from '@/components/chat/MessageCard.vue'
import AssistantBlock from '@/components/chat/AssistantBlock.vue'
import ComposerBar from '@/components/chat/ComposerBar.vue'

const store = useChatStore()
const bodyEl = ref(null)
const composerRef = ref(null)
const panelVisible = ref(false)
const overlayVisible = ref(false)
const overlayIndex = ref(0)
const overlayItems = ref([])
const overlayCurrent = computed(() => overlayItems.value[overlayIndex.value] || null)

const suggestions = ['正当防卫的规定', '缓刑的适用条件', '自首与坦白的区别']

function scrollToBottom() {
  nextTick(() => {
    if (bodyEl.value) bodyEl.value.scrollTop = bodyEl.value.scrollHeight
  })
}

watch(
  () => store.streamingEntry,
  () => { if (store.generating) scrollToBottom() },
  { deep: true }
)

function handleOpenChunk(data) {
  overlayItems.value = data.all || []
  overlayIndex.value = data.index ?? 0
  overlayVisible.value = true
}

async function handleNewConversation() {
  if (store.generating) return
  await store.createConversation()
  panelVisible.value = false
  scrollToBottom()
}

async function handleDeleteConversation(id) {
  if (store.generating) return
  await store.deleteConversation(id)
  scrollToBottom()
}

async function handleBatchDelete() {
  if (!store.batchSelected.size) return
  await store.batchDelete()
  store.exitBatchMode()
  scrollToBottom()
}

async function handleResetMemory() {
  if (store.generating) return
  await store.resetMemory()
}

function handleKeydown(e) {
  if (e.key === '/' && document.activeElement?.tagName !== 'TEXTAREA' && document.activeElement?.tagName !== 'INPUT') {
    e.preventDefault()
    composerRef.value?.focus()
  }
}

onMounted(async () => {
  document.addEventListener('keydown', handleKeydown)
  await store.loadFromServer()
  await store.loadMessages(store.activeId)
  await store.syncAgentMemory()
  scrollToBottom()
})
</script>

<style scoped>
.chat-canvas {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  height: 100vh;
  max-width: 840px;
  margin: 0 auto;
}

.canvas-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  flex-shrink: 0;
}

.topbar-btn {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-md);
  color: var(--text-muted);
  transition: all var(--transition-fast);
}
.topbar-btn:hover { color: var(--text-primary); background: rgba(99, 102, 241, 0.08); }

.topbar-center {
  flex: 1;
  text-align: center;
}

.topbar-title {
  font-family: var(--font-display);
  font-size: 0.9375rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-secondary);
}

.canvas-body {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 0 20px;
  scroll-behavior: smooth;
}

.canvas-messages {
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  padding-top: 24px;
  padding-bottom: 8px;
}

.welcome-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 48px 24px;
  min-height: 50vh;
}

.welcome-icon {
  width: 64px;
  height: 64px;
  border-radius: var(--radius-xl);
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
  display: grid;
  place-items: center;
  font-size: 1.75rem;
  font-weight: 800;
  color: #fff;
  margin-bottom: 24px;
  box-shadow: 0 8px 32px var(--accent-glow);
  animation: pulse-glow 3s ease-in-out infinite;
}

.welcome-heading {
  font-family: var(--font-display);
  font-size: 1.75rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  margin-bottom: 8px;
}

.welcome-desc {
  font-size: 0.9375rem;
  color: var(--text-secondary);
  max-width: 420px;
  line-height: 1.6;
  margin-bottom: 28px;
}

.welcome-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
}

.welcome-chip {
  padding: 9px 18px;
  border-radius: var(--radius-full);
  border: 1px solid var(--glass-border);
  background: var(--bg-card);
  color: var(--text-secondary);
  font-size: 0.8125rem;
  cursor: pointer;
  transition: all var(--transition-fast);
}
.welcome-chip:hover {
  border-color: var(--glass-border-hover);
  color: var(--text-primary);
  background: var(--bg-card-hover);
  transform: translateY(-2px);
}

.messages-flow {
  display: flex;
  flex-direction: column;
}

.canvas-footer {
  flex-shrink: 0;
  padding: 12px 20px 24px;
}

.composer-wrap {
  max-width: 720px;
  margin: 0 auto;
}

.welcome-enter-active { transition: all 0.3s ease-out; }
.welcome-leave-active { transition: all 0.2s ease-in; }
.welcome-enter-from,
.welcome-leave-to { opacity: 0; transform: translateY(12px); }

.rag-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 800;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(5, 7, 14, 0.7);
  backdrop-filter: blur(4px);
  padding: 24px;
}

.rag-modal {
  width: min(680px, 100%);
  max-height: 80vh;
  display: flex;
  flex-direction: column;
}

.rag-modal-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 18px 20px;
  border-bottom: 1px solid var(--glass-border);
}

.rag-modal-title {
  font-weight: 600;
  font-size: 0.9375rem;
}

.rag-modal-idx {
  font-size: 0.75rem;
  color: var(--text-muted);
  background: var(--bg-input);
  padding: 3px 8px;
  border-radius: var(--radius-full);
}

.rag-modal-close {
  margin-left: auto;
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  transition: all var(--transition-fast);
}
.rag-modal-close:hover { color: var(--text-primary); background: rgba(239, 68, 68, 0.08); }

.rag-modal-tags {
  display: flex;
  gap: 6px;
  padding: 10px 20px;
  flex-wrap: wrap;
}

.rag-tag {
  font-size: 0.6875rem;
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  background: var(--bg-input);
  color: var(--text-secondary);
  border: 1px solid var(--glass-border);
}
.rag-tag.score {
  background: rgba(16, 185, 129, 0.08);
  border-color: rgba(16, 185, 129, 0.15);
  color: var(--success);
}

.rag-modal-text {
  flex: 1;
  padding: 16px 20px;
  overflow-y: auto;
  font-size: 0.875rem;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
  color: #d4d8e3;
}

.rag-modal-nav {
  display: flex;
  justify-content: space-between;
  padding: 14px 20px;
  border-top: 1px solid var(--glass-border);
}

.rag-nav-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 14px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  background: var(--bg-input);
  color: var(--text-secondary);
  font-size: 0.8125rem;
  cursor: pointer;
  transition: all var(--transition-fast);
}
.rag-nav-btn:hover:not(:disabled) { border-color: var(--glass-border-hover); color: var(--text-primary); }
.rag-nav-btn:disabled { opacity: 0.35; cursor: not-allowed; }

.modal-enter-active { transition: all 0.25s ease-out; }
.modal-leave-active { transition: all 0.2s ease-in; }
.modal-enter-from,
.modal-leave-to { opacity: 0; }
.modal-enter-from .rag-modal { transform: scale(0.96) translateY(12px); }
.modal-leave-to .rag-modal { transform: scale(0.96) translateY(12px); }
</style>
