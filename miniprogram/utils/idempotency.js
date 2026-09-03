function createIdempotencyKey(now = Date.now(), random = Math.random()) {
  return `ad_${now.toString(36)}_${Math.floor(random * 1e12).toString(36).padStart(8, '0')}`
}

function createOperationKey(prefix = 'op', now = Date.now(), random = Math.random()) {
  const safePrefix = String(prefix).replace(/[^A-Za-z0-9_-]/g, '').slice(0, 16) || 'op'
  return `${safePrefix}_${now.toString(36)}_${Math.floor(random * 1e12).toString(36).padStart(8, '0')}`
}

module.exports = { createIdempotencyKey, createOperationKey }
