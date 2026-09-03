const test = require('node:test')
const assert = require('node:assert/strict')
const { QUALITY_OPTIONS, normalizeRequestedQuality, qualityOption } = require('../utils/quality')

test('quality selector exposes original, 720p and 540p in product order', () => {
  assert.deepEqual(QUALITY_OPTIONS.map((item) => item.value), ['original', '720p', '540p'])
  assert.equal(qualityOption('original').label, '原视频')
})

test('unknown quality safely falls back to original', () => {
  assert.equal(normalizeRequestedQuality('4k'), 'original')
  assert.equal(normalizeRequestedQuality('720p'), '720p')
})
