import { defineStore } from 'pinia'
import { ref } from 'vue'
import { kbApi } from '@/api/knowledge'

export const useKbStore = defineStore('knowledge', () => {
  const documents = ref([])
  const loading = ref(false)
  const uploading = ref(false)
  const uploadResult = ref(null)
  const uploadProgress = ref(null)
  const healthData = ref(null)
  const chunksStats = ref(null)
  const activeJobs = ref([])

  async function loadDocuments() {
    loading.value = true
    try {
      const res = await kbApi.getDocuments()
      if (res.ok) documents.value = res.documents || []
      else documents.value = []
    } catch {
      documents.value = []
    } finally {
      loading.value = false
    }
  }

  async function uploadDocument(file) {
    uploading.value = true
    uploadResult.value = null
    uploadProgress.value = null
    try {
      const res = await kbApi.uploadDocument(file)
      if (!res.ok) {
        uploadResult.value = { type: 'error', message: res.message || '上传失败' }
        uploading.value = false
        return null
      }
      if (res.job_id) {
        uploadProgress.value = { jobId: res.job_id, fileName: file.name, total: 0, done: 0, status: 'processing' }
        return res.job_id
      }
      uploadResult.value = { type: 'success', message: res.message || '文档已成功入库' }
      uploading.value = false
      return null
    } catch (err) {
      uploadResult.value = { type: 'error', message: '网络错误: ' + err.message }
      uploading.value = false
      return null
    }
  }

  async function pollJob(jobId) {
    try {
      const res = await kbApi.getJobStatus(jobId)
      if (!res.ok || !res.job_id) return null
      const total = res.total_chunks || 0
      const done = res.embedded_chunks || 0
      const pct = total > 0 ? Math.min(Math.round((done / total) * 100), 100) : 0
      uploadProgress.value = { jobId, fileName: res.source || '', total, done, status: res.status, pct }

      if (res.status === 'done') {
        uploading.value = false
        uploadResult.value = { type: 'success', message: `入库完成 - ${res.source} (${res.chunk_count || 0} chunks)` }
        return 'done'
      }
      if (res.status === 'failed') {
        uploading.value = false
        uploadResult.value = { type: 'error', message: res.error_message || '入库失败' }
        return 'failed'
      }
      return 'processing'
    } catch {
      return null
    }
  }

  async function deleteDocument(source) {
    const prev = [...documents.value]
    documents.value = documents.value.filter((d) => d.source !== source)
    try {
      const res = await kbApi.deleteDocument(source)
      if (!res.ok) {
        documents.value = prev
        return false
      }
      return true
    } catch {
      documents.value = prev
      return false
    }
  }

  async function loadHealth() {
    try {
      const res = await kbApi.getHealth()
      healthData.value = res
    } catch (err) {
      healthData.value = { error: err.message }
    }
  }

  async function loadChunkStats() {
    try {
      const res = await kbApi.getChunkStats()
      if (res.ok) chunksStats.value = res.stats
      else chunksStats.value = null
    } catch {
      chunksStats.value = null
    }
  }

  async function loadActiveJobs() {
    try {
      const res = await kbApi.getActiveJobs()
      if (res.ok) activeJobs.value = res.jobs || []
    } catch {
      activeJobs.value = []
    }
  }

  function resetUpload() {
    uploading.value = false
    uploadResult.value = null
    uploadProgress.value = null
  }

  return {
    documents, loading, uploading, uploadResult, uploadProgress,
    healthData, chunksStats, activeJobs,
    loadDocuments, uploadDocument, pollJob, deleteDocument,
    loadHealth, loadChunkStats, loadActiveJobs, resetUpload,
  }
})
