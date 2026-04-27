import { marked } from 'marked'
import DOMPurify from 'dompurify'

marked.setOptions({ gfm: true, breaks: true })

export function renderMarkdown(text) {
  if (!text) return ''
  try {
    return DOMPurify.sanitize(marked.parse(text))
  } catch {
    return escapeHtml(text).replaceAll('\n', '<br>')
  }
}

export function escapeHtml(value) {
  return String(value || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}

export function makeId() {
  return `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

export function nowTs() {
  return Date.now()
}

export function formatTime(ts) {
  const d = new Date(ts || Date.now())
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

export function formatTimeShort(isoString) {
  if (!isoString) return '-'
  try {
    const d = new Date(isoString)
    const now = new Date()
    const isToday = d.toDateString() === now.toDateString()
    if (isToday) {
      return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    }
    return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }) +
      ' ' + d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  } catch {
    return isoString
  }
}

export function getFileIcon(filename) {
  const ext = (filename || '').split('.').pop().toLowerCase()
  const map = { pdf: 'pdf', docx: 'docx', md: 'md', markdown: 'md', txt: 'txt' }
  return map[ext] || 'txt'
}

export function parseRagResult(rawText) {
  const lines = rawText.split('\n')
  const meta = { query: '', count: '', strategy: '', timing: '', rewriteSummary: '', rewriteVariants: [] }
  const chunks = []
  let inChunks = false
  let currentChunk = null

  for (const line of lines) {
    if (/^命中片段\s*:/.test(line)) { inChunks = true; continue }
    if (!inChunks) {
      if (/^最终查询\s*:/.test(line)) meta.query = line.replace(/^最终查询\s*:\s*/, '')
      else if (/^命中数量\s*:/.test(line)) meta.count = line.replace(/^命中数量\s*:\s*/, '')
      else if (/^自动改写检索\s*:/.test(line)) meta.rewriteSummary = line.replace(/^自动改写检索\s*:\s*/, '')
      else if (/^-\s*第\d+路\s*\|/.test(line)) meta.rewriteVariants.push(line.replace(/^\s*-\s*/, ''))
      else if (/^检索策略\s*:/.test(line)) meta.strategy = line.replace(/^检索策略\s*:\s*/, '')
      else if (/^检索耗时\s*:/.test(line)) meta.timing = line.replace(/^检索耗时\s*:\s*/, '')
    } else {
      const headerMatch = line.match(/^\s*(\d+)\.\s+来源:\s*(.+?)\s*\|\s*chunk:\s*(.+?)\s*\|\s*hybrid:\s*([\d.]+)/)
      if (headerMatch) {
        if (currentChunk) chunks.push(currentChunk)
        currentChunk = { index: parseInt(headerMatch[1]), source: headerMatch[2], chunkId: headerMatch[3], hybrid: parseFloat(headerMatch[4]), text: '' }
        continue
      }
      if (currentChunk && /^\s+内容:\s*/.test(line)) {
        currentChunk.text += line.replace(/^\s+内容:\s*/, '') + '\n'
      } else if (currentChunk && !headerMatch && line.trim()) {
        currentChunk.text += line + '\n'
      }
    }
  }
  if (currentChunk) chunks.push(currentChunk)
  return { meta, chunks }
}

export function isRagResult(text) {
  return /命中片段/.test(text) && /来源:.*\|.*chunk:.*\|.*hybrid:/m.test(text)
}
