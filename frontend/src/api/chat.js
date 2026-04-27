const BASE = ''

async function request(method, url, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } }
  if (body !== undefined && body !== null) opts.body = JSON.stringify(body)
  const res = await fetch(BASE + url, opts)
  return res.json()
}

export const chatApi = {
  getState: () => request('GET', '/api/chat/state'),
  resetMemory: () => request('POST', '/api/chat/reset'),
  syncMessages: (messages) => request('POST', '/api/chat/sync', { messages }),
  listConversations: () => request('GET', '/api/chat/conversations'),
  createConversation: (title) => request('POST', '/api/chat/conversations', { title: title || '新对话' }),
  getConversation: (id) => request('GET', `/api/chat/conversations/${id}`),
  activateConversation: (id) => request('POST', `/api/chat/conversations/${id}/activate`),
  deleteConversation: (id) => request('DELETE', `/api/chat/conversations/${id}`),
  batchDeleteConversations: (ids) => request('POST', '/api/chat/conversations/batch-delete', { ids }),
  appendMessage: (convId, role, content) => request('POST', `/api/chat/conversations/${convId}/messages`, { role, content }),
  updateMessage: (convId, msgId, action, data) => {
    data = { ...data, action }
    return fetch(BASE + `/api/chat/conversations/${convId}/messages/${msgId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
  },
  touchConversation: (id) => request('POST', `/api/chat/conversations/${id}/touch`),
  updateTitle: (id, title) => request('POST', `/api/chat/conversations/${id}/title`, { title }),
}

export function parseSSEChunk(chunk) {
  if (!chunk.trim()) return null
  const lines = chunk.split('\n')
  let event = 'message'
  const dataParts = []
  for (const line of lines) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) dataParts.push(line.slice(5).trim())
  }
  if (!dataParts.length) return { event, payload: {} }
  try {
    return { event, payload: JSON.parse(dataParts.join('\n')) }
  } catch (err) {
    return { event: 'error', payload: { message: `数据解析失败: ${err}` } }
  }
}

export async function streamChat(message, signal, callbacks) {
  const response = await fetch(BASE + '/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
    signal,
  })

  if (!response.ok) {
    const err = await response.json().catch(() => ({ message: `请求失败(${response.status})` }))
    callbacks.onError?.(err.message || '请求失败')
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const chunks = buffer.split('\n\n')
    buffer = chunks.pop() || ''
    for (const raw of chunks) {
      const parsed = parseSSEChunk(raw)
      if (!parsed) continue
      const { event, payload } = parsed
      if (event === 'content') callbacks.onContent?.(payload.delta)
      else if (event === 'reasoning') callbacks.onReasoning?.(payload.delta)
      else if (event === 'phase') callbacks.onPhase?.(payload)
      else if (event === 'tool_call') callbacks.onToolCall?.(payload)
      else if (event === 'tool_result') callbacks.onToolResult?.(payload)
      else if (event === 'token_stats') callbacks.onTokenStats?.(payload)
      else if (event === 'done') { callbacks.onDone?.(); return }
      else if (event === 'error') callbacks.onError?.(payload.message)
    }
  }
}
