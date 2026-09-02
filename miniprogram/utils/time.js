function parseServerTime(value) {
  const timestamp = Date.parse(value || '')
  return Number.isFinite(timestamp) ? timestamp : Date.now()
}

function entitlementView(entitlement, nowMs = Date.now()) {
  if (!entitlement || !entitlement.entitled || !entitlement.unlock_until) {
    return { entitled: false, label: '观看广告可解锁 24 小时下载', expiresLabel: '未解锁' }
  }
  const until = Date.parse(entitlement.unlock_until)
  const left = until - nowMs
  if (!Number.isFinite(until) || left <= 0) {
    return { entitled: false, label: '观看广告可解锁 24 小时下载', expiresLabel: '已过期' }
  }
  const hours = Math.floor(left / 3600000)
  const minutes = Math.floor((left % 3600000) / 60000)
  return {
    entitled: true,
    label: `下载已解锁 · 剩余 ${hours}小时${minutes}分`,
    expiresLabel: new Date(until).toLocaleString('zh-CN', { hour12: false })
  }
}

module.exports = { parseServerTime, entitlementView }

