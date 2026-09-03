const test = require('node:test')
const assert = require('node:assert/strict')
const { assertProductionSafe, assertRuntimeSafe } = require('../config')

const validProduction = {
  APP_ENV: 'production',
  MOCK_API: false,
  MOCK_WECHAT_AUTH: false,
  MOCK_REWARDED_AD: false,
  API_BASE_URL: 'https://media-api.valid-domain.cn/api/v1',
  REWARDED_AD_UNIT_ID: 'adunit-1234567890abcdef',
  BANNER_AD_UNIT_ID: 'adunit-fedcba0987654321'
}

test('production rejects Mock configuration', () => {
  assert.throws(() => assertProductionSafe({ APP_ENV: 'production', MOCK_API: true }), /禁止启用 Mock/)
})

test('production requires https and both ad units', () => {
  assert.throws(() => assertProductionSafe({
    APP_ENV: 'production', MOCK_API: false, MOCK_WECHAT_AUTH: false, MOCK_REWARDED_AD: false,
    API_BASE_URL: 'http://example.com', REWARDED_AD_UNIT_ID: 'r', BANNER_AD_UNIT_ID: 'b'
  }), /HTTPS/)
  assert.equal(assertProductionSafe(validProduction), true)
})

test('production rejects placeholders and unsafe release packaging', () => {
  assert.throws(() => assertProductionSafe({
    ...validProduction,
    API_BASE_URL: 'https://api.example.com/api/v1',
    REWARDED_AD_UNIT_ID: 'adunit-replace-with-real-id'
  }), /非占位/)
  assert.throws(() => assertRuntimeSafe({ APP_ENV: 'development' }, 'trial'), /禁止打包开发 Mock/)
  assert.throws(() => assertRuntimeSafe({ APP_ENV: 'development' }, 'release'), /禁止打包开发 Mock/)
  assert.equal(assertRuntimeSafe({ APP_ENV: 'development' }, 'develop'), true)
  assert.equal(assertRuntimeSafe(validProduction, 'release'), true)
})
