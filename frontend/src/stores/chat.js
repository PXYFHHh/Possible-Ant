import { defineStore } from 'pinia'
import { ref, shallowRef, computed } from 'vue'
import { chatApi } from '@/api/chat'
import { streamChat } from '@/api/chat'
import { makeId, nowTs } from '@/utils'

export const useChatStore = defineStore('chat', () => {
  const conversations = ref([])
  const activeId = ref('')
  const generating = ref(false)
  const abortController = ref(null)
  const batchMode = ref(false)
  const batchSelected = ref(new Set())
  const searchQuery = ref('')
  const streamingEntry = shallowRef(null)
  const liveTypingRounds = ref([])

  const activeConversation = computed(() => {
    const conv = conversations.value.find((c) => c.id === activeId.value)
    if (conv) return conv
    const empty = createEmptyConversation()
    conversations.value.unshift(empty)
    activeId.value = empty.id
    return empty
  })

  const filteredConversations = computed(() => {
    let list = [...conversations.value].sort((a, b) => b.updatedAt - a.updatedAt)
    if (searchQuery.value) {
      const q = searchQuery.value.toLowerCase()
      list = list.filter((c) => c.title.toLowerCase().includes(q))
    }
    return list
  })

  const messages = computed(() => activeConversation.value.messages || [])

  function createEmptyConversation() {
    return {
      id: makeId(),
      title: '新对话',
      createdAt: nowTs(),
      updatedAt: nowTs(),
      messages: [],
    }
  }

  function buildTitle(conv) {
    const firstUser = (conv.messages || []).find((m) => m.role === 'user' && String(m.content || '').trim())
    if (!firstUser) return '新对话'
    const text = String(firstUser.content).replace(/\s+/g, ' ').trim()
    return text.length > 24 ? text.slice(0, 24) + '...' : text
  }

  function touchConv(conv) {
    conv.updatedAt = nowTs()
    conv.title = buildTitle(conv)
    chatApi.touchConversation(conv.id).catch(() => {})
  }

  async function loadFromServer() {
    try {
      const res = await chatApi.listConversations()
      conversations.value = (res.conversations || []).map((c) => ({
        ...c,
        messages: c.messages || [],
      }))
      activeId.value = res.activeId || ''
      if (!conversations.value.length) {
        const r = await chatApi.createConversation()
        if (r.ok && r.conversation) {
          conversations.value.push({ ...r.conversation, messages: [] })
          activeId.value = r.conversation.id
        }
      } else if (!activeId.value || !conversations.value.some((c) => c.id === activeId.value)) {
        activeId.value = conversations.value[0].id
      }
    } catch {
      if (!conversations.value.length) {
        const empty = createEmptyConversation()
        conversations.value.push(empty)
        activeId.value = empty.id
      }
    }
  }

  async function loadMessages(convId) {
    try {
      const res = await chatApi.getConversation(convId)
      if (res.ok && res.messages) {
        const conv = conversations.value.find((c) => c.id === convId)
        if (conv) conv.messages = res.messages
      }
    } catch { /* ignore */ }
  }

  async function syncAgentMemory() {
    const conv = activeConversation.value
    if (!conv) return
    const convMessages = conv.messages || []
    await chatApi.resetMemory(conv.id)
    if (convMessages.length) {
      await chatApi.syncMessages(convMessages, conv.id)
    }
  }

  async function switchConversation(id) {
    if (id === activeId.value) return
    if (!conversations.value.some((c) => c.id === id)) return
    activeId.value = id
    await loadMessages(id)
    await syncAgentMemory()
    chatApi.activateConversation(id).catch(() => {})
  }

  async function createConversation() {
    const conv = await chatApi.createConversation().then((r) => (r.ok && r.conversation) ? { ...r.conversation, messages: [] } : null).catch(() => null)
    if (!conv) {
      const empty = createEmptyConversation()
      conversations.value.unshift(empty)
      activeId.value = empty.id
      return empty
    }
    conversations.value.unshift(conv)
    activeId.value = conv.id
    await fetch('/api/chat/reset', { method: 'POST' }).catch(() => {})
    return conv
  }

  async function deleteConversation(id) {
    const idx = conversations.value.findIndex((c) => c.id === id)
    if (idx < 0) return
    const deletingActive = id === activeId.value
    await chatApi.deleteConversation(id).catch(() => {})
    conversations.value.splice(idx, 1)
    if (!conversations.value.length) {
      const empty = createEmptyConversation()
      conversations.value.push(empty)
      activeId.value = empty.id
      await fetch('/api/chat/reset', { method: 'POST' }).catch(() => {})
    } else if (deletingActive) {
      activeId.value = conversations.value[0].id
      await loadMessages(activeId.value)
      await syncAgentMemory()
    }
  }

  async function batchDelete() {
    const ids = [...batchSelected.value]
    if (!ids.length) return
    await chatApi.batchDeleteConversations(ids).catch(() => {})
    conversations.value = conversations.value.filter((c) => !ids.includes(c.id))
    batchSelected.value.clear()
    const needSync = ids.includes(activeId.value)
    if (!conversations.value.length) {
      const empty = createEmptyConversation()
      conversations.value.push(empty)
      activeId.value = empty.id
      await fetch('/api/chat/reset', { method: 'POST' }).catch(() => {})
    } else if (!activeId.value || needSync) {
      activeId.value = conversations.value[0].id
      await loadMessages(activeId.value)
      await syncAgentMemory()
    }
    exitBatchMode()
  }

  function addUserMessage(text) {
    const conv = activeConversation.value
    const msg = { role: 'user', content: text }
    conv.messages.push(msg)
    touchConv(conv)
    chatApi.appendMessage(conv.id, 'user', text).then((r) => {
      if (r.ok && r.message) msg.dbId = r.message.id
    })
  }

  function addAssistantEntry() {
    const conv = activeConversation.value
    const entry = { role: 'assistant', segments: [], token_stats: null }
    conv.messages.push(entry)
    touchConv(conv)
    chatApi.appendMessage(conv.id, 'assistant').then((r) => {
      if (r.ok && r.message) entry.dbId = r.message.id
    })
    return entry
  }

  async function addAssistantEntryAsync() {
    const conv = activeConversation.value
    const entry = { role: 'assistant', segments: [], token_stats: null }
    conv.messages.push(entry)
    touchConv(conv)
    const r = await chatApi.appendMessage(conv.id, 'assistant')
    if (r.ok && r.message) entry.dbId = r.message.id
    return entry
  }

  function dbAppendText(convId, msgDbId, delta) {
    chatApi.updateMessage(convId, msgDbId, 'append_text', { content: delta }).catch(() => {})
  }

  function dbAppendReasoning(convId, msgDbId, delta) {
    chatApi.updateMessage(convId, msgDbId, 'append_reasoning', { content: delta }).catch(() => {})
  }

  function dbAddToolCall(convId, msgDbId, name, args) {
    chatApi.updateMessage(convId, msgDbId, 'add_tool_call', { name, args }).catch(() => {})
  }

  function dbSetToolResult(convId, msgDbId, result) {
    chatApi.updateMessage(convId, msgDbId, 'set_tool_result', { result }).catch(() => {})
  }

  function dbSetTokenStats(convId, msgDbId, stats) {
    chatApi.updateMessage(convId, msgDbId, 'set_token_stats', { stats }).catch(() => {})
  }

  async function resetMemory() {
    try { await fetch('/api/chat/reset', { method: 'POST' }) } catch (_) {}
  }

  function toggleBatchSelect(id) {
    const s = new Set(batchSelected.value)
    if (s.has(id)) s.delete(id)
    else s.add(id)
    batchSelected.value = s
  }

  function enterBatchMode() {
    batchMode.value = true
    batchSelected.value = new Set()
  }

  function exitBatchMode() {
    batchMode.value = false
    batchSelected.value = new Set()
  }

  function selectAllBatch() {
    const allIds = conversations.value.map((c) => c.id)
    if (batchSelected.value.size >= allIds.length) {
      batchSelected.value = new Set()
    } else {
      batchSelected.value = new Set(allIds)
    }
  }

  function getDisplayEntry(msg) {
    if (generating.value && streamingEntry.value && msg === activeConversation.value.messages[activeConversation.value.messages.length - 1]) {
      return streamingEntry.value
    }
    return msg
  }

  async function sendMessage(text) {
    if (generating.value) return

    addUserMessage(text)

    const rawEntry = await addAssistantEntryAsync()
    streamingEntry.value = { ...rawEntry, segments: [] }
    liveTypingRounds.value = []

    generating.value = true
    abortController.value = new AbortController()

    let currentRound = null
    let currentToolCalls = []
    let hasOutput = false

    function getRound() {
      if (!currentRound) {
        currentRound = { type: null }
        liveTypingRounds.value = [...liveTypingRounds.value, currentRound]
      }
      return currentRound
    }

    function syncDisplay() {
      streamingEntry.value = {
        ...rawEntry,
        segments: rawEntry.segments.map((s) => ({ ...s })),
        token_stats: rawEntry.token_stats ? { ...rawEntry.token_stats } : null,
      }
    }

    try {
      await streamChat(text, activeId.value, abortController.value.signal, {
        onContent(delta) {
          getRound().type = 'text'
          const idx = rawEntry.segments.length - 1
          const lastSeg = rawEntry.segments[idx]
          if (lastSeg?.type === 'text') {
            rawEntry.segments[idx] = { ...lastSeg, content: lastSeg.content + delta }
          } else {
            rawEntry.segments.push({ type: 'text', content: delta })
          }
          hasOutput = true
          dbAppendText(activeId.value, rawEntry.dbId, delta)
          syncDisplay()
        },
        onReasoning(delta) {
          getRound().type = 'reasoning'
          const idx = rawEntry.segments.length - 1
          const lastSeg = rawEntry.segments[idx]
          if (lastSeg?.type === 'reasoning') {
            rawEntry.segments[idx] = { ...lastSeg, content: lastSeg.content + delta }
          } else {
            rawEntry.segments.push({ type: 'reasoning', content: delta })
          }
          hasOutput = true
          dbAppendReasoning(activeId.value, rawEntry.dbId, delta)
          syncDisplay()
        },
        onPhase(payload) {
          if (payload?.type === 'thinking') {
            currentRound = null
            liveTypingRounds.value = [...liveTypingRounds.value, { type: null }]
          }
        },
        onToolCall(payload) {
          const seg = { type: 'tool_call', name: payload.name || 'tool', args: payload.args || {}, result: '' }
          rawEntry.segments.push(seg)
          currentToolCalls.push({ name: seg.name, segment: seg, done: false })
          hasOutput = true
          currentRound = null
          dbAddToolCall(activeId.value, rawEntry.dbId, seg.name, seg.args)
          syncDisplay()
        },
        onToolResult(payload) {
          const matched = currentToolCalls.find((t) => t.name === (payload.name || '') && !t.done) ||
                          currentToolCalls.find((t) => !t.done)
          if (matched) {
            matched.segment.result = payload.result || ''
            matched.done = true
            dbSetToolResult(activeId.value, rawEntry.dbId, matched.segment.result)
            syncDisplay()
          }
        },
        onTokenStats(payload) {
          rawEntry.token_stats = {
            input_tokens: Number(payload.input_tokens || 0),
            output_tokens: Number(payload.output_tokens || 0),
            llm_calls: Number(payload.llm_calls || 0),
          }
          dbSetTokenStats(activeId.value, rawEntry.dbId, rawEntry.token_stats)
          syncDisplay()
        },
        onDone() {
          if (!hasOutput) {
            rawEntry.segments.push({ type: 'text', content: '(无输出)' })
          }
          syncDisplay()
        },
        onError(errMsg) {
          rawEntry.segments.push({ type: 'text', content: `❌ ${errMsg}` })
          syncDisplay()
        },
      })
    } catch (err) {
      if (err.name === 'AbortError') {
        if (!hasOutput) rawEntry.segments.push({ type: 'text', content: '⏹️ 已停止生成' })
      } else {
        rawEntry.segments.push({ type: 'text', content: `❌ ${err.message || err}` })
      }
      syncDisplay()
    } finally {
      liveTypingRounds.value = []
      generating.value = false
      abortController.value = null
      touchConv(activeConversation.value)
      streamingEntry.value = null
    }
  }

  function stopMessage() {
    if (abortController.value) {
      abortController.value.abort()
      generating.value = false
    }
  }

  return {
    conversations, activeId, generating, abortController,
    batchMode, batchSelected, searchQuery,
    streamingEntry, liveTypingRounds,
    activeConversation, filteredConversations, messages,
    loadFromServer, loadMessages, switchConversation, createConversation,
    deleteConversation, batchDelete, syncAgentMemory,
    addUserMessage, addAssistantEntry, addAssistantEntryAsync,
    dbAppendText, dbAppendReasoning, dbAddToolCall, dbSetToolResult, dbSetTokenStats,
    resetMemory, buildTitle, touchConv,
    toggleBatchSelect, enterBatchMode, exitBatchMode, selectAllBatch,
    getDisplayEntry, sendMessage, stopMessage,
  }
})
