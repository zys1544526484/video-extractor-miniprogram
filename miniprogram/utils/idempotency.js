function createIdempotencyKey(now = Date.now(), random = Math.random()) {
  return `ad_${now.toString(36)}_${Math.floor(random * 1e12).toString(36).padStart(8, '0')}`
}

module.exports = { createIdempotencyKey }

