const test = require('node:test')
const assert = require('node:assert/strict')

const values = new Map()
global.wx = {
  getStorageSync(key) { return values.get(key) || '' },
  setStorageSync(key, value) { values.set(key, value) },
  removeStorageSync(key) { values.delete(key) }
}

const storage = require('../services/storage')

test('active parse job storage supports multiple jobs and exact removal', () => {
  storage.clearParseJobs()
  storage.upsertParseJob({ job_id: 'pj_1', source_text: 'one' })
  storage.upsertParseJob({ job_id: 'pj_2', source_text: 'two' })
  assert.deepEqual(storage.getParseJobs().map((item) => item.job_id), ['pj_2', 'pj_1'])

  storage.removeParseJob('pj_2')
  assert.deepEqual(storage.getParseJobs().map((item) => item.job_id), ['pj_1'])
})

test('legacy single job is migrated without being lost', () => {
  storage.clearParseJobs()
  values.set('video_extractor_parse_job', { job_id: 'pj_legacy' })
  assert.equal(storage.getParseJobs()[0].job_id, 'pj_legacy')
  assert.equal(values.has('video_extractor_parse_job'), false)
})

test('parse retry draft can be consumed once', () => {
  storage.setParseDraft({ source_text: 'https://example.com/video', requested_quality: '540p' })
  assert.equal(storage.takeParseDraft().requested_quality, '540p')
  assert.equal(storage.takeParseDraft(), null)
})
