const test = require('node:test')
const assert = require('node:assert/strict')

const storage = new Map()
global.wx = {
  getStorageSync(key) { return storage.get(key) || '' },
  setStorageSync(key, value) { storage.set(key, value) },
  removeStorageSync(key) { storage.delete(key) }
}

const mockApi = require('../services/mock-api')
const api = require('../services/api')

test('large parse jobs remain visible for the full server processing window', () => {
  assert.equal(api.PARSE_JOB_MAX_WAIT_MS, 65 * 60 * 1000)
})

test('mock parse job is idempotent and progresses to one complete result', async () => {
  const options = {
    method: 'POST',
    header: { 'Idempotency-Key': 'parse_mock_job_01' },
    data: { text: 'https://example.com/video.mp4', quality: '540p' }
  }
  const created = await mockApi.handle('/parse', options)
  const repeated = await mockApi.handle('/parse', options)
  assert.equal(repeated.job.job_id, created.job.job_id)

  await new Promise((resolve) => setTimeout(resolve, 950))
  const completed = await mockApi.handle(`/parse/jobs/${created.job.job_id}`, { method: 'GET' })
  assert.equal(completed.job.status, 'ready')
  assert.equal(completed.job.progress, 100)
  assert.equal(completed.job.result.requested_quality, '540p')
})
