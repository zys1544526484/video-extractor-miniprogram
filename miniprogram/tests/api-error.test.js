const test = require('node:test')
const assert = require('node:assert/strict')

const { presentApiError } = require('../utils/api-error')

test('platform changes use a clear maintenance message', () => {
  const result = presentApiError({ code: 'PLATFORM_CHANGED', message: 'upstream failed' })
  assert.equal(result.title, '当前平台暂时受限')
  assert.match(result.message, /更换其他公开链接|稍后再试/)
  assert.doesNotMatch(result.message, /upstream/)
})

test('ordinary API errors retain the stable user message', () => {
  const result = presentApiError({ code: 'URL_NOT_FOUND', message: '未识别到有效链接' })
  assert.deepEqual(result, { title: '提取失败', message: '未识别到有效链接' })
})

test('oversized selected quality asks the user to choose a lower tier', () => {
  const result = presentApiError({
    code: 'MEDIA_TOO_LARGE',
    message: '所选原视频预计超过 180MiB，请改选较低画质'
  })
  assert.equal(result.title, '所选画质文件过大')
  assert.match(result.message, /改选较低画质/)
})
