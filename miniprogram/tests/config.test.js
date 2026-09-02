const test = require('node:test')
const assert = require('node:assert/strict')
const { assertProductionSafe } = require('../config')

test('production rejects Mock configuration', () => {
  assert.throws(() => assertProductionSafe({ APP_ENV: 'production', MOCK_API: true }), /禁止启用 Mock/)
})

test('production requires https and both ad units', () => {
  assert.throws(() => assertProductionSafe({
    APP_ENV: 'production', MOCK_API: false, MOCK_WECHAT_AUTH: false, MOCK_REWARDED_AD: false,
    API_BASE_URL: 'http://example.com', REWARDED_AD_UNIT_ID: 'r', BANNER_AD_UNIT_ID: 'b'
  }), /HTTPS/)
  assert.equal(assertProductionSafe({
    APP_ENV: 'production', MOCK_API: false, MOCK_WECHAT_AUTH: false, MOCK_REWARDED_AD: false,
    API_BASE_URL: 'https://example.com', REWARDED_AD_UNIT_ID: 'r', BANNER_AD_UNIT_ID: 'b'
  }), true)
})

