const { getConfig } = require('../config/index')
const storage = require('./storage')
const mockApi = require('./mock-api')
const { normalizeRequestedQuality } = require('../utils/quality')

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
  parse(text, quality = 'original') {
    const config = getConfig()
    const timeout = config.APP_ENV === 'development' ? 600000 : 30000
    return request('/parse', {
      method: 'POST',
      data: { text, quality: normalizeRequestedQuality(quality) },
      timeout
    })
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
