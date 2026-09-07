const test = require('node:test')
const assert = require('node:assert/strict')

let pageDefinition
let navigatedUrl = ''
const values = new Map([['video_extractor_auth_token', 'test-token']])

global.wx = {
  getStorageSync(key) { return values.get(key) || '' },
  setStorageSync(key, value) { values.set(key, value) },
  removeStorageSync(key) { values.delete(key) },
  request(options) {
    options.success({
      statusCode: 202,
      data: {
        success: true,
        request_id: 'req_test_parse',
        job: {
          job_id: 'job-auto-route',
          status: 'queued',
          progress: 0,
          stage: '等待处理',
          source_url: 'https://example.com/video.mp4',
          requested_quality: 'original'
        }
      }
    })
  },
  navigateTo(options) { navigatedUrl = options.url }
}
global.Page = (definition) => { pageDefinition = definition }
global.getApp = () => ({ globalData: { serverOffsetMs: 0 } })

require('../pages/index/index')

test('startParse navigates to result with the created job id', async () => {
  navigatedUrl = ''
  const context = {
    data: {
      busy: false,
      atJobLimit: false,
      inputText: 'https://example.com/video.mp4'
    },
    setState(state) {
      this.data.state = state
      this.data.busy = state === 'checking' || state === 'parsing'
    },
    setData(value) {
      this.data = { ...this.data, ...value }
    },
    refreshActiveJobs: async () => {}
  }
  await pageDefinition.startParse.call(context)
  assert.equal(navigatedUrl, '/pages/result/result?job_id=job-auto-route')
})
