const test = require('node:test')
const assert = require('node:assert/strict')

global.wx = {
  getStorageSync() { return '' }
}

const { createDownloadService } = require('../services/download')

test('mock download reports progress but does not claim a real save', async () => {
  const progress = []
  const service = createDownloadService({ wxApi: {}, config: { MOCK_API: true } })
  const result = await service.downloadAndSave('/assets/mock-video.mp4', (value) => progress.push(value))
  assert.equal(result.mock, true)
  assert.equal(result.saved, false)
  assert.equal(progress.at(-1), 100)
})

