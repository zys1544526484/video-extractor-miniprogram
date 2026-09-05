const test = require('node:test')
const assert = require('node:assert/strict')

let pageDefinition
const toasts = []
let copiedValue = ''
const storedValues = new Map()

global.wx = {
  getStorageSync(key) {
    return storedValues.get(key) || ''
  },
  setStorageSync(key, value) {
    storedValues.set(key, value)
  },
  setClipboardData(options) {
    copiedValue = options.data
    options.success()
  },
  showToast(options) {
    toasts.push(options)
  },
  showModal(options) {
    toasts.push({ modal: true, ...options })
  }
}
global.getApp = () => ({ globalData: { serverOffsetMs: 0 } })
global.Page = (definition) => { pageDefinition = definition }

require('../pages/result/result')

test('copyCurrentLink refreshes an expired token before copying', async () => {
  toasts.length = 0
  copiedValue = ''
  const refreshed = {
    title: '作品',
    download_url: 'https://api.example.com/api/v1/media/renewed/download',
    expires_at: new Date(Date.now() + 60000).toISOString()
  }
  const context = {
    data: { result: { expires_at: new Date(Date.now() - 1000).toISOString() } },
    ensureFreshResult: async () => refreshed
  }
  await pageDefinition.copyCurrentLink.call(context)
  assert.equal(copiedValue, refreshed.download_url)
  assert.equal(toasts.filter((item) => item.icon === 'success').length, 1)
})

test('copyCurrentLink does not claim success when token refresh fails', async () => {
  toasts.length = 0
  copiedValue = ''
  const context = {
    data: { result: { expires_at: new Date(Date.now() - 1000).toISOString() } },
    ensureFreshResult: async () => { throw new Error('安全链接刷新失败') }
  }
  await pageDefinition.copyCurrentLink.call(context)
  assert.equal(copiedValue, '')
  assert.equal(toasts.some((item) => item.icon === 'success'), false)
  assert.equal(toasts.at(-1).icon, 'none')
})

test('loadResult falls back with a prompt when the persisted source is gone', () => {
  storedValues.set('video_extractor_selected_sources', { 'job-a': 'source-2' })
  const context = {
    data: {},
    setData(value) {
      this.lastData = value
    },
    sourceLabel: pageDefinition.sourceLabel,
    sourceSizeLabel: pageDefinition.sourceSizeLabel,
    infoText: pageDefinition.infoText,
    notifySourceFallback: pageDefinition.notifySourceFallback
  }
  pageDefinition.loadResult.call(context, {
    job_id: 'job-a',
    title: '多源作品',
    platform: 'generic',
    sources: [{
      source_id: 'source-1',
      quality_label: '720P',
      size_bytes: 100,
      preview_url: 'https://api.example.com/api/v1/media/one/preview',
      download_url: 'https://api.example.com/api/v1/media/one/download'
    }],
    selected_source_id: 'source-1',
    expires_at: new Date(Date.now() + 60000).toISOString()
  })
  assert.equal(context.lastData.selectedSourceId, 'source-1')
  assert.equal(toasts.some((item) => item.modal && item.title === '视频源已过期'), true)
})
