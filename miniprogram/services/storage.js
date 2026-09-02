const TOKEN_KEY = 'video_extractor_auth_token'
const ENTITLEMENT_KEY = 'video_extractor_download_entitlement'
const RESULT_KEY = 'video_extractor_current_result'

function getToken() {
  return wx.getStorageSync(TOKEN_KEY) || ''
}

function setToken(token) {
  wx.setStorageSync(TOKEN_KEY, token || '')
}

function clearToken() {
  wx.removeStorageSync(TOKEN_KEY)
}

function getEntitlement() {
  return wx.getStorageSync(ENTITLEMENT_KEY) || null
}

function setEntitlement(value) {
  wx.setStorageSync(ENTITLEMENT_KEY, value || null)
}

function setCurrentResult(result) {
  wx.setStorageSync(RESULT_KEY, result || null)
}

function getCurrentResult() {
  return wx.getStorageSync(RESULT_KEY) || null
}

function clearCurrentResult() {
  wx.removeStorageSync(RESULT_KEY)
}

module.exports = {
  getToken,
  setToken,
  clearToken,
  getEntitlement,
  setEntitlement,
  setCurrentResult,
  getCurrentResult,
  clearCurrentResult
}

