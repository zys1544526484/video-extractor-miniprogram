const test = require('node:test')
const assert = require('node:assert/strict')

const storage = new Map()
global.wx = {
  getStorageSync(key) { return storage.get(key) || '' },
  setStorageSync(key, value) { storage.set(key, value) }
}

const mockApi = require('../services/mock-api')

test('mock flow creates an ad attempt before granting entitlement', async () => {
  storage.clear()
  const attempt = await mockApi.handle('/entitlement/ad-attempt', { method: 'POST', data: {} })
  assert.equal(attempt.attempt_required, true)
  assert.match(attempt.attempt_token, /^mock_attempt_/)

  await assert.rejects(
    mockApi.handle('/entitlement/ad-complete', { method: 'POST', data: {} }),
    { code: 'AD_CONFIRM_INVALID' }
  )

  const complete = await mockApi.handle('/entitlement/ad-complete', {
    method: 'POST',
    data: { attempt_token: attempt.attempt_token }
  })
  assert.equal(complete.entitled, true)
  assert.ok(Date.parse(complete.unlock_until) > Date.now())
})
