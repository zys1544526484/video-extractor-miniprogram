const { normalizeShareText, hasHttpUrl } = require('../utils/input')
const { normalizeRequestedQuality, qualityOption } = require('../utils/quality')

const MOCK_ENTITLEMENT_KEY = 'video_extractor_mock_entitlement'

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function serverNow() {
  return new Date().toISOString()
}

function currentEntitlement() {
  const value = wx.getStorageSync(MOCK_ENTITLEMENT_KEY) || null
  const until = value && Date.parse(value.unlock_until)
  return {
    entitled: Boolean(until && until > Date.now()),
    unlock_until: until && until > Date.now() ? value.unlock_until : null,
    server_time: serverNow()
  }
}

async function handle(path, options = {}) {
  await wait(path === '/parse' ? 850 : 120)

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
    return {
      success: true,
      request_id: 'req_mock_parse',
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
        expires_at: new Date(Date.now() + 15 * 60000).toISOString(),
        watermark_status: 'source_original',
        notice: '开发模式示例，不代表真实平台解析结果。'
      }
    }
  }

  const error = new Error('Mock API 未实现该接口')
  error.code = 'INTERNAL_ERROR'
  throw error
}

module.exports = { handle, currentEntitlement }
