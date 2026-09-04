const test = require('node:test')
const assert = require('node:assert/strict')
const { isTokenExpired } = require('../utils/result-expiry')

test('result refresh uses token expiry while media retention remains longer', () => {
  const now = Date.parse('2026-09-04T00:16:00.000Z')
  const result = {
    expires_at: '2026-09-04T00:15:00.000Z',
    media_expires_at: '2026-09-05T00:00:00.000Z'
  }
  assert.equal(isTokenExpired(result, now), true)
  assert.equal(isTokenExpired({ ...result, expires_at: '2026-09-04T00:20:00.000Z' }, now), false)
})
