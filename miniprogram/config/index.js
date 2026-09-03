const env = require('./env')

const PLACEHOLDER_PATTERN = /(example\.(?:com|net|org)|replace|placeholder|change[-_]?me|your[-_]?)/i

function isValidApiBaseUrl(value) {
  const match = /^https:\/\/([^/?#:]+)(\/[^?#]*)?$/.exec(String(value || ''))
  if (!match) return false
  const host = match[1].toLowerCase()
  const path = (match[2] || '').replace(/\/+$/, '')
  if (!host || host === 'localhost' || /^\d+(?:\.\d+){3}$/.test(host)) return false
  if (PLACEHOLDER_PATTERN.test(host)) return false
  return path === '/api/v1'
}

function isValidAdUnitId(value) {
  const text = String(value || '')
  return /^adunit-[A-Za-z0-9_-]{8,}$/.test(text) && !PLACEHOLDER_PATTERN.test(text)
}

function getConfig() {
  return Object.freeze({ ...env })
}

function assertProductionSafe(config) {
  if (config.APP_ENV !== 'production') return true
  if (config.MOCK_API !== false || config.MOCK_WECHAT_AUTH !== false || config.MOCK_REWARDED_AD !== false) {
    throw new Error('生产环境禁止启用 Mock 能力')
  }
  if (!isValidApiBaseUrl(config.API_BASE_URL)) {
    throw new Error('生产 API_BASE_URL 必须是无端口、非占位的 HTTPS 域名，并以 /api/v1 结尾')
  }
  if (!isValidAdUnitId(config.REWARDED_AD_UNIT_ID) || !isValidAdUnitId(config.BANNER_AD_UNIT_ID)) {
    throw new Error('生产环境必须配置非占位的真实广告单元')
  }
  return true
}

function assertRuntimeSafe(config, envVersion) {
  if (envVersion === 'trial' || envVersion === 'release') {
    if (config.APP_ENV !== 'production') {
      throw new Error('体验版和正式版必须使用 production 配置，禁止打包开发 Mock')
    }
    assertProductionSafe(config)
  }
  return true
}

module.exports = {
  getConfig,
  assertProductionSafe,
  assertRuntimeSafe,
  isValidApiBaseUrl,
  isValidAdUnitId
}
