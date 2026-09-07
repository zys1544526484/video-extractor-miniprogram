const test = require('node:test')
const assert = require('node:assert/strict')
const api = require('../services/api')

let pageDefinition
const toasts = []
let copiedValue = ''
const storedValues = new Map()
storedValues.set('video_extractor_auth_token', 'test-token')

global.wx = {
  getStorageSync(key) {
    return storedValues.get(key) || ''
  },
  setStorageSync(key, value) {
    storedValues.set(key, value)
  },
  removeStorageSync(key) {
    storedValues.delete(key)
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

test('result page polls a created job and renders the completed result', async () => {
  const originalWait = api.waitForParseJob
  api.waitForParseJob = async (jobId, onProgress) => {
    onProgress({ job_id: jobId, status: 'processing', progress: 42, stage: '解析公开页面', source_url: 'https://example.com/a' })
    onProgress({ job_id: jobId, status: 'ready', progress: 100, stage: '处理完成', source_url: 'https://example.com/a' })
    return {
      title: '已完成作品',
      platform: 'generic',
      media_type: 'video',
      preview_url: 'https://api.example.com/api/v1/media/a/preview',
      download_url: 'https://api.example.com/api/v1/media/a/download',
      expires_at: new Date(Date.now() + 60000).toISOString(),
      sources: [{
        source_id: 'source-1',
        quality_label: '720P',
        size_bytes: 100,
        preview_url: 'https://api.example.com/api/v1/media/a/preview',
        download_url: 'https://api.example.com/api/v1/media/a/download'
      }]
    }
  }
  const context = {
    ...pageDefinition,
    data: {},
    pageVisible: true,
    pollGeneration: 0,
    setData(value) { this.data = { ...this.data, ...value } }
  }
  try {
    await pageDefinition.startJobPolling.call(context, 'job-success')
    assert.equal(context.data.state, 'ready')
    assert.equal(context.data.progress, 0)
    assert.equal(context.data.result.title, '已完成作品')
  } finally {
    api.waitForParseJob = originalWait
  }
})

test('result page exposes backend error code and reason after polling failure', async () => {
  const originalWait = api.waitForParseJob
  api.waitForParseJob = async (jobId, onProgress) => {
    onProgress({ job_id: jobId, status: 'processing', progress: 18, stage: '解析公开页面', source_url: 'https://example.com/a' })
    const error = new Error('该内容不可公开访问')
    error.code = 'CONTENT_NOT_PUBLIC'
    throw error
  }
  const context = {
    ...pageDefinition,
    data: {},
    pageVisible: true,
    pollGeneration: 0,
    setData(value) { this.data = { ...this.data, ...value } }
  }
  try {
    await pageDefinition.startJobPolling.call(context, 'job-failed')
    assert.equal(context.data.state, 'error')
    assert.equal(context.data.parseErrorCode, 'CONTENT_NOT_PUBLIC')
    assert.equal(context.data.parseErrorMessage, '该内容不可公开访问')
  } finally {
    api.waitForParseJob = originalWait
  }
})

test('result page resumes one fresh poll after hide then immediate show', async () => {
  const originalWait = api.waitForParseJob
  let calls = 0
  let resolveFirst
  let firstShouldContinue
  const oldResult = {
    title: '旧轮询结果',
    platform: 'generic',
    media_type: 'video',
    preview_url: 'https://api.example.com/api/v1/media/old/preview',
    download_url: 'https://api.example.com/api/v1/media/old/download',
    expires_at: new Date(Date.now() + 60000).toISOString(),
    sources: [{
      source_id: 'source-1',
      preview_url: 'https://api.example.com/api/v1/media/old/preview',
      download_url: 'https://api.example.com/api/v1/media/old/download'
    }]
  }
  const resumedResult = {
    ...oldResult,
    title: '恢复后的结果',
    preview_url: 'https://api.example.com/api/v1/media/new/preview',
    download_url: 'https://api.example.com/api/v1/media/new/download',
    sources: [{
      source_id: 'source-1',
      preview_url: 'https://api.example.com/api/v1/media/new/preview',
      download_url: 'https://api.example.com/api/v1/media/new/download'
    }]
  }
  api.waitForParseJob = (jobId, onProgress, options) => {
    calls += 1
    if (calls === 1) {
      onProgress({ job_id: jobId, status: 'processing', progress: 36, stage: '解析公开页面' })
      firstShouldContinue = options.shouldContinue
      return new Promise((resolve) => { resolveFirst = resolve })
    }
    onProgress({ job_id: jobId, status: 'ready', progress: 100, stage: '处理完成' })
    return Promise.resolve(resumedResult)
  }
  const context = {
    ...pageDefinition,
    data: { jobId: 'job-resume', state: 'loading', result: null },
    pageVisible: true,
    pollGeneration: 0,
    setData(value) { this.data = { ...this.data, ...value } }
  }
  try {
    const oldPoll = pageDefinition.startJobPolling.call(context, 'job-resume')
    await Promise.resolve()
    assert.equal(calls, 1)

    pageDefinition.onHide.call(context)
    pageDefinition.onShow.call(context)
    assert.equal(firstShouldContinue(), false)
    assert.equal(calls, 1)

    resolveFirst(oldResult)
    await oldPoll
    await new Promise((resolve) => setImmediate(resolve))
    await new Promise((resolve) => setImmediate(resolve))

    assert.equal(calls, 2)
    assert.equal(context.data.state, 'ready')
    assert.equal(context.data.result.title, '恢复后的结果')
    assert.equal(context.data.result.download_url, resumedResult.download_url)
  } finally {
    api.waitForParseJob = originalWait
  }
})
