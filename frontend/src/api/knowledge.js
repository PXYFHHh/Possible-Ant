const BASE = ''

async function request(method, url, body) {
  const opts = { method, headers: {} }
  if (body) opts.body = body
  const res = await fetch(BASE + url, opts)
  return res.json().catch(() => ({ ok: false, message: '请求失败' }))
}

export const kbApi = {
  getDocuments: () => request('GET', '/api/kb/documents'),
  getHealth: () => request('GET', '/api/kb/health'),
  getJobStatus: (jobId) => request('GET', `/api/kb/job/${encodeURIComponent(jobId)}`),
  getActiveJobs: () => request('GET', '/api/kb/jobs/active'),
  getChunkStats: () => request('GET', '/api/kb/chunks/stats'),
  deleteDocument: (source) => request('DELETE', `/api/kb/documents/${encodeURIComponent(source)}`),
  uploadDocument: (file) => {
    const form = new FormData()
    form.append('file', file)
    return request('POST', '/api/kb/upload', form)
  },
}
