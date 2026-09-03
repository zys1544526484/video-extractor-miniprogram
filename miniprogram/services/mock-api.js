const { normalizeShareText, hasHttpUrl } = require('../utils/input')
const { normalizeRequestedQuality, qualityOption } = require('../utils/quality')
const { getConfig } = require('../config/index')

const MOCK_ENTITLEMENT_KEY = 'video_extractor_mock_entitlement'
const MOCK_JOBS = new Map()

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function serverNow() {
  return new Date().toISOString()
}

function currentEntitlement() {
  if (getConfig().DOWNLOAD_ACCESS_MODE === 'free') {
    return {
      access_mode: 'free',
      can_download: true,
      entitled: true,
      unlock_until: null,
      server_time: serverNow()
    }
  }
  const value = wx.getStorageSync(MOCK_ENTITLEMENT_KEY) || null
  const until = value && Date.parse(value.unlock_until)
  return {
    access_mode: 'rewarded_ad',
    can_download: Boolean(until && until > Date.now()),
    entitled: Boolean(until && until > Date.now()),
    unlock_until: until && until > Date.now() ? value.unlock_until : null,
    server_time: serverNow()
  }
}

async function handle(path, options = {}) {
  await wait(path === '/parse' ? 120 : 80)

  if (path === '/auth/wechat' && options.method === 'POST') {
    return {
      success: true,
      request_id: 'req_mock_auth',
      token: 'mock_session_token',
      expires_in: 604800,
      user: currentEntitlement()
    }
  }

  if (path === '/entitlement' && options.method === 'GET') {
    return { success: true, request_id: 'req_mock_entitlement', ...currentEntitlement() }
  }

  if (path === '/entitlement/ad-attempt' && options.method === 'POST') {
    if (getConfig().DOWNLOAD_ACCESS_MODE === 'free') {
      const error = new Error('当前版本无需观看广告，可直接下载')
      error.code = 'FEATURE_DISABLED'
      throw error
    }
    const current = currentEntitlement()
    return {
      success: true,
      request_id: 'req_mock_ad_attempt',
      ...current,
      attempt_required: !current.entitled,
      attempt_token: current.entitled ? null : 'mock_attempt_' + Date.now(),
      attempt_expires_at: current.entitled ? null : new Date(Date.now() + 10 * 60000).toISOString()
    }
  }

  if (path === '/entitlement/ad-complete' && options.method === 'POST') {
    if (getConfig().DOWNLOAD_ACCESS_MODE === 'free') {
      const error = new Error('当前版本无需观看广告，可直接下载')
      error.code = 'FEATURE_DISABLED'
      throw error
    }
    if (!options.data || !options.data.attempt_token) {
      const error = new Error('广告确认凭证无效')
      error.code = 'AD_CONFIRM_INVALID'
      throw error
    }
    const existing = currentEntitlement()
    if (existing.entitled) return { success: true, request_id: 'req_mock_ad', ...existing }
    const value = {
      entitled: true,
      unlock_until: new Date(Date.now() + 24 * 3600000).toISOString(),
      server_time: serverNow()
    }
    wx.setStorageSync(MOCK_ENTITLEMENT_KEY, value)
    return { success: true, request_id: 'req_mock_ad', ...value }
  }

  if (path === '/parse' && options.method === 'POST') {
    const text = normalizeShareText(options.data && options.data.text)
    const requestedQuality = normalizeRequestedQuality(options.data && options.data.quality)
    if (!hasHttpUrl(text)) {
      const error = new Error('未识别到有效链接')
      error.code = 'URL_NOT_FOUND'
      error.retryable = false
      throw error
    }
    const key = options.header && options.header['Idempotency-Key']
    const existing = key && [...MOCK_JOBS.values()].find((item) => item.key === key)
    if (existing) return { success: true, request_id: 'req_mock_parse', job: mockJobView(existing) }
    const job = {
      key,
      job_id: `pj_mock_${Date.now()}`,
      createdAt: Date.now(),
      result: {
        session_id: 'mock_session',
        platform: '抖音',
        title: '示例视频标题',
        cover_url: '',
        media_type: 'video',
        duration_seconds: 42,
        size_bytes: 5320000,
        quality_label: qualityOption(requestedQuality).label,
        requested_quality: requestedQuality,
        preview_url: '/assets/mock-video.mp4',
        download_url: '/assets/mock-video.mp4',
        expires_at: new Date(Date.now() + 2 * 3600000).toISOString(),
        watermark_status: 'source_original',
        notice: '开发模式示例，不代表真实平台解析结果。'
      }
    }
    MOCK_JOBS.set(job.job_id, job)
    return { success: true, request_id: 'req_mock_parse', job: mockJobView(job) }
  }

  const jobMatch = /^\/parse\/jobs\/([^/]+)$/.exec(path)
  if (jobMatch && options.method === 'GET') {
    const job = MOCK_JOBS.get(jobMatch[1])
    if (!job) {
      const error = new Error('提取任务不存在')
      error.code = 'JOB_NOT_FOUND'
      throw error
    }
    return { success: true, request_id: 'req_mock_job', job: mockJobView(job) }
  }
  if (jobMatch && options.method === 'DELETE') {
    const job = MOCK_JOBS.get(jobMatch[1])
    if (job) job.cancelled = true
    return { success: true, request_id: 'req_mock_cancel', job: mockJobView(job) }
  }

  const error = new Error('Mock API 未实现该接口')
  error.code = 'INTERNAL_ERROR'
  throw error
}

function mockJobView(job) {
  if (!job) return { status: 'cancelled', progress: 0, stage: '已取消' }
  const elapsed = Date.now() - job.createdAt
  if (job.cancelled) return { job_id: job.job_id, status: 'cancelled', progress: 0, stage: '已取消' }
  if (elapsed < 250) return { job_id: job.job_id, status: 'queued', progress: 0, stage: '等待处理' }
  if (elapsed < 900) {
    const progress = Math.min(92, Math.round((elapsed - 250) / 7))
    return { job_id: job.job_id, status: 'processing', progress, stage: '准备完整视频' }
  }
  return { job_id: job.job_id, status: 'ready', progress: 100, stage: '处理完成', result: job.result }
}

module.exports = { handle, currentEntitlement }
