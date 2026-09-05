const test = require('node:test')
const assert = require('node:assert/strict')
const { historyJobView, platformLabel, shortDate } = require('../utils/history')

test('history view clearly separates active ready and expired jobs', () => {
  const active = historyJobView({ status: 'processing', platform: 'bilibili', progress: 41 })
  const ready = historyJobView({
    status: 'ready',
    platform: 'douyin',
    media_available: true,
    summary: { title: '示例', quality_label: '720P H.264', size_bytes: 10 * 1024 * 1024 }
  })
  const expired = historyJobView({ status: 'expired', platform: 'weibo', media_available: false })
  const failed = historyJobView({
    status: 'failed',
    platform: 'xiaohongshu',
    error: { code: 'CONTENT_RESTRICTED', message: '该内容不可公开访问' }
  })

  assert.equal(active.active, true)
  assert.equal(active.platform_label, '哔哩哔哩')
  assert.equal(ready.ready, true)
  assert.equal(ready.action_label, '打开结果')
  assert.match(ready.detail, /10\.0MB/)
  assert.equal(expired.action_label, '再次提取')
  assert.equal(failed.detail, 'CONTENT_RESTRICTED：该内容不可公开访问')
})

test('history labels have stable fallbacks', () => {
  assert.equal(platformLabel('unknown-platform'), 'unknown-platform')
  assert.equal(shortDate('invalid'), '')
})
