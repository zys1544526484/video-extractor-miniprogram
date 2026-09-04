function isTokenExpired(result, now = Date.now()) {
  if (!result) return true
  const expiresAt = Date.parse(result.expires_at)
  return !Number.isFinite(expiresAt) || expiresAt <= now
}

module.exports = { isTokenExpired }
