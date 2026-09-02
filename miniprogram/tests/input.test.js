const test = require('node:test')
const assert = require('node:assert/strict')
const { normalizeShareText, hasHttpUrl } = require('../utils/input')

test('normalizeShareText trims and removes null bytes', () => {
  assert.equal(normalizeShareText('  复制\u0000 https://example.com/a  '), '复制 https://example.com/a')
})

test('hasHttpUrl accepts share text and rejects non-http text', () => {
  assert.equal(hasHttpUrl('看看这个 https://v.example.com/a?id=1 复制打开'), true)
  assert.equal(hasHttpUrl('file:///tmp/video.mp4'), false)
  assert.equal(hasHttpUrl('只有普通文字'), false)
})

test('input is capped at 5000 characters', () => {
  assert.equal(normalizeShareText('x'.repeat(6000)).length, 5000)
})

