const api = require('./api')
const storage = require('./storage')
const { parseServerTime } = require('../utils/time')

function saveEntitlement(result) {
  const value = {
    access_mode: result.access_mode || 'rewarded_ad',
    can_download: Boolean(result.can_download || result.entitled),
    entitled: Boolean(result.entitled),
    unlock_until: result.unlock_until || null,
    server_time: result.server_time || new Date().toISOString()
  }
  storage.setEntitlement(value)
  const app = getApp()
  app.globalData.entitlement = value
  app.globalData.serverOffsetMs = parseServerTime(value.server_time) - Date.now()
  return value
}

async function refreshEntitlement() {
  return saveEntitlement(await api.entitlement())
}

async function startAdAttempt() {
  return api.adAttempt()
}

async function completeAd(idempotencyKey, attemptToken) {
  return saveEntitlement(await api.adComplete(idempotencyKey, attemptToken))
}

module.exports = { refreshEntitlement, startAdAttempt, completeAd, saveEntitlement }
