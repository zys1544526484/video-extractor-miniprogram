const test = require('node:test')
const assert = require('node:assert/strict')

const storage = new Map()
global.wx = {
  getStorageSync(key) { return storage.get(key) || '' },
  setStorageSync(key, value) { storage.set(key, value) }
}

const mockApi = require('../services/mock-api')

test('mock free mode grants download access and disables ad endpoints', async () => {
  storage.clear()
  const access = await mockApi.handle('/entitlement', { method: 'GET' })
  assert.equal(access.access_mode, 'free')
  assert.equal(access.can_download, true)
  assert.equal(access.unlock_until, null)

  await assert.rejects(
    mockApi.handle('/entitlement/ad-attempt', { method: 'POST', data: {} }),
    { code: 'FEATURE_DISABLED' }
  )
})
