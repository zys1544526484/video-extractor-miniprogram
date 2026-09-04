const test = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')
const { spawnSync } = require('node:child_process')
const { assertProductionSafe, assertRuntimeSafe } = require('../config')

const validProduction = {
  APP_ENV: 'production',
  MOCK_API: false,
  MOCK_WECHAT_AUTH: false,
  MOCK_REWARDED_AD: false,
  API_BASE_URL: 'https://media-api.valid-domain.cn/api/v1',
  DOWNLOAD_ACCESS_MODE: 'free',
  REWARDED_AD_UNIT_ID: '',
  BANNER_AD_UNIT_ID: ''
}

test('production rejects Mock configuration', () => {
  assert.throws(() => assertProductionSafe({ APP_ENV: 'production', MOCK_API: true }), /禁止启用 Mock/)
})

test('development config cannot pass production validation', () => {
  assert.throws(() => assertProductionSafe({ APP_ENV: 'development' }), /production 配置/)
  const result = spawnSync(
    process.execPath,
    [path.resolve(__dirname, '../../scripts/validate_miniprogram.js'), '--production'],
    {
      cwd: path.resolve(__dirname, '../..'),
      encoding: 'utf8',
      env: { ...process.env, MINIPROGRAM_VALIDATE_SYNTHETIC: '1', VALIDATE_PRODUCTION_APP_ENV: 'development' }
    }
  )
  assert.notEqual(result.status, 0)
  assert.match(`${result.stdout}\n${result.stderr}`, /production 配置/)
})

test('production free mode requires https but not ad units', () => {
  assert.throws(() => assertProductionSafe({
    APP_ENV: 'production', MOCK_API: false, MOCK_WECHAT_AUTH: false, MOCK_REWARDED_AD: false,
    API_BASE_URL: 'http://example.com', DOWNLOAD_ACCESS_MODE: 'free', REWARDED_AD_UNIT_ID: '', BANNER_AD_UNIT_ID: ''
  }), /HTTPS/)
  assert.equal(assertProductionSafe(validProduction), true)
})

test('production rewarded mode requires both ad units', () => {
  assert.throws(() => assertProductionSafe({
    ...validProduction,
    DOWNLOAD_ACCESS_MODE: 'rewarded_ad'
  }), /真实广告单元/)
  assert.equal(assertProductionSafe({
    ...validProduction,
    DOWNLOAD_ACCESS_MODE: 'rewarded_ad',
    REWARDED_AD_UNIT_ID: 'adunit-1234567890abcdef',
    BANNER_AD_UNIT_ID: 'adunit-fedcba0987654321'
  }), true)
})

test('production rejects placeholders and unsafe release packaging', () => {
  assert.throws(() => assertProductionSafe({
    ...validProduction,
    API_BASE_URL: 'https://api.example.com/api/v1'
  }), /非占位/)
  assert.throws(() => assertProductionSafe({ ...validProduction, DOWNLOAD_ACCESS_MODE: 'invalid' }), /DOWNLOAD_ACCESS_MODE/)
  assert.throws(() => assertRuntimeSafe({ APP_ENV: 'development' }, 'trial'), /禁止打包开发 Mock/)
  assert.throws(() => assertRuntimeSafe({ APP_ENV: 'development' }, 'release'), /禁止打包开发 Mock/)
  assert.equal(assertRuntimeSafe({ APP_ENV: 'development' }, 'develop'), true)
  assert.equal(assertRuntimeSafe(validProduction, 'release'), true)
})
