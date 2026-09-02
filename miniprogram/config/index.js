const env = require('./env')

function getConfig() {
  return Object.freeze({ ...env })
}

function assertProductionSafe(config) {
  if (config.APP_ENV !== 'production') return true
  if (config.MOCK_API || config.MOCK_WECHAT_AUTH || config.MOCK_REWARDED_AD) {
    throw new Error('生产环境禁止启用 Mock 能力')
  }
  if (!/^https:\/\//.test(config.API_BASE_URL)) {
    throw new Error('生产 API_BASE_URL 必须使用 HTTPS')
  }
  if (!config.REWARDED_AD_UNIT_ID || !config.BANNER_AD_UNIT_ID) {
    throw new Error('生产环境必须配置真实广告单元')
  }
  return true
}

module.exports = { getConfig, assertProductionSafe }

