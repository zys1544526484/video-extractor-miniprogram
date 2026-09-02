const test = require('node:test')
const assert = require('node:assert/strict')
const { createRewardedAdService } = require('../services/ad')

function fakeWx(closeResult) {
  let onClose
  let onError
  const ad = {
    onClose(handler) { onClose = handler },
    offClose() { onClose = null },
    onError(handler) { onError = handler },
    offError() { onError = null },
    async show() { setImmediate(() => onClose(closeResult)) },
    async load() {},
    destroy() { onClose = null; onError = null }
  }
  return { createRewardedVideoAd: () => ad }
}

const realConfig = { MOCK_REWARDED_AD: false, REWARDED_AD_UNIT_ID: 'adunit-test' }

test('reward only when isEnded is true', async () => {
  const completed = createRewardedAdService({ wxApi: fakeWx({ isEnded: true }), config: realConfig })
  completed.init()
  assert.equal((await completed.show()).completed, true)
  completed.destroy()

  const closed = createRewardedAdService({ wxApi: fakeWx({ isEnded: false }), config: realConfig })
  closed.init()
  assert.equal((await closed.show()).completed, false)
  closed.destroy()
})

test('mock ad outcome remains explicit', async () => {
  const service = createRewardedAdService({ wxApi: {}, config: { MOCK_REWARDED_AD: true, MOCK_AD_OUTCOME: 'closed' } })
  const result = await service.show()
  assert.deepEqual(result, { completed: false, mock: true })
})

