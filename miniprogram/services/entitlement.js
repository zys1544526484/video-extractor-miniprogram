const api = require('./api')
const storage = require('./storage')
const { parseServerTime } = require('../utils/time')

function saveEntitlement(result) {
  const value = {
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

async function completeAd(idempotencyKey) {
  return saveEntitlement(await api.adComplete(idempotencyKey))
}

module.exports = { refreshEntitlement, completeAd, saveEntitlement }

