const PLATFORM_LIMIT_CODES = new Set([
  'PLATFORM_CHANGED',
  'PLATFORM_UNSUPPORTED',
  'CONTENT_RESTRICTED',
  'MEDIA_FORMAT_UNSUPPORTED'
])

function presentApiError(error = {}) {
  if (PLATFORM_LIMIT_CODES.has(error.code)) {
    return {
      title: '当前平台暂时受限',
      message: '该平台的公开页面解析规则可能已变化，请更换其他公开链接或稍后再试。'
    }
  }
  if (error.code === 'PARSE_TIMEOUT' || error.code === 'RATE_LIMITED') {
    return {
      title: '请求暂未完成',
      message: error.message || '请求较多，请稍后再试。'
    }
  }
  return {
    title: '提取失败',
    message: error.message || '暂时无法提取'
  }
}

module.exports = { presentApiError }
