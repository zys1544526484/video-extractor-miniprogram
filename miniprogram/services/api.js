const { getConfig } = require('../config/index')
const storage = require('./storage')
const mockApi = require('./mock-api')
const { normalizeRequestedQuality } = require('../utils/quality')
const { createOperationKey } = require('../utils/idempotency')

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function parseJobError(job) {
  const detail = (job && job.error) || {}
  const error = new Error(detail.message || '提取失败')
  error.code = detail.code || 'PARSE_FAILED'
  error.retryable = Boolean(detail.retryable)
  return error
}

function toApiError(payload, statusCode) {
  const detail = payload && payload.error ? payload.error : {}
  const error = new Error(detail.message || `请求失败（${statusCode || '网络错误'}）`)
  error.code = detail.code || 'NETWORK_ERROR'
  error.retryable = Boolean(detail.retryable)
  error.requestId = payload && payload.request_id
  error.statusCode = statusCode
  return error
}

async function request(path, options = {}) {
  const config = getConfig()
  const method = options.method || 'GET'
  if (config.MOCK_API) return mockApi.handle(path, { ...options, method })

  const token = storage.getToken()
  const header = { 'content-type': 'application/json', ...(options.header || {}) }
  if (options.auth !== false && token) header.Authorization = `Bearer ${token}`

  try {
    return await new Promise((resolve, reject) => {
      wx.request({
        url: `${config.API_BASE_URL}${path}`,
        method,
        data: options.data,
        header,
        timeout: options.timeout || 30000,
        success(response) {
          const payload = response.data || {}
          if (response.statusCode >= 200 && response.statusCode < 300 && payload.success !== false) {
            resolve(payload)
          } else {
            reject(toApiError(payload, response.statusCode))
          }
        },
        fail(error) {
          const apiError = new Error(error.errMsg || '网络连接失败')
          apiError.code = 'NETWORK_ERROR'
          apiError.retryable = true
          reject(apiError)
        }
      })
    })
  } catch (error) {
    const mayRefresh = options.auth !== false && options.retryAuth !== false
    if (mayRefresh && (error.statusCode === 401 || error.code === 'AUTH_REQUIRED')) {
      const auth = require('./auth')
      await auth.refreshAuth()
      return request(path, { ...options, retryAuth: false })
    }
    throw error
  }
}

module.exports = {
  request,
  createParse(text, quality = 'original', idempotencyKey = createOperationKey('parse')) {
    return request('/parse', {
      method: 'POST',
      data: { text, quality: normalizeRequestedQuality(quality) },
      header: { 'Idempotency-Key': idempotencyKey },
      timeout: 30000
    })
  },
  parseJob(jobId) {
    return request(`/parse/jobs/${jobId}`, { method: 'GET' })
  },
  cancelParse(jobId) {
    return request(`/parse/jobs/${jobId}`, { method: 'DELETE' })
  },
  async waitForParseJob(jobId, onProgress, options = {}) {
    const interval = options.pollInterval == null ? 1500 : options.pollInterval
    const maxWait = options.maxWait == null ? 30 * 60 * 1000 : options.maxWait
    const started = Date.now()
    while (Date.now() - started <= maxWait) {
      if (options.shouldContinue && !options.shouldContinue()) return null
      const response = await request(`/parse/jobs/${jobId}`, { method: 'GET' })
      const job = response.job
      if (onProgress) onProgress(job)
      if (job.status === 'ready') return job.result
      if (job.status === 'failed') throw parseJobError(job)
      if (job.status === 'cancelled') {
        const error = new Error('提取任务已取消')
        error.code = 'JOB_CANCELLED'
        throw error
      }
      if (job.status === 'expired') {
        const error = new Error('提取任务已过期，请重新提交')
        error.code = 'JOB_EXPIRED'
        throw error
      }
      await wait(interval)
    }
    const error = new Error('处理时间较长，任务仍在后台继续，可稍后返回查看')
    error.code = 'PARSE_POLL_TIMEOUT'
    error.retryable = true
    throw error
  },
  async parse(text, quality = 'original', onProgress) {
    const created = await this.createParse(text, quality)
    return { result: await this.waitForParseJob(created.job.job_id, onProgress) }
  },
  entitlement() {
    return request('/entitlement', { method: 'GET' })
  },
  adAttempt() {
    return request('/entitlement/ad-attempt', { method: 'POST', data: {} })
  },
  adComplete(idempotencyKey, attemptToken) {
    return request('/entitlement/ad-complete', {
      method: 'POST',
      data: { attempt_token: attemptToken },
      header: { 'Idempotency-Key': idempotencyKey }
    })
  }
}
