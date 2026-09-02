const api = require('./api')
const storage = require('./storage')

function wxLogin() {
  return new Promise((resolve, reject) => {
    wx.login({
      timeout: 10000,
      success(result) {
        if (result.code) resolve(result.code)
        else reject(new Error('微信登录未返回 code'))
      },
      fail(error) {
        reject(new Error(error.errMsg || '微信登录失败'))
      }
    })
  })
}

async function refreshAuth() {
  storage.clearToken()
  const code = await wxLogin()
  const result = await api.request('/auth/wechat', {
    method: 'POST',
    data: { code },
    auth: false,
    retryAuth: false
  })
  storage.setToken(result.token)
  if (result.user) storage.setEntitlement(result.user)
  return result
}

async function ensureAuth() {
  const token = storage.getToken()
  if (token) return token
  const result = await refreshAuth()
  return result.token
}

module.exports = { ensureAuth, refreshAuth }

