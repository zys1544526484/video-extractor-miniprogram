const { getConfig, assertProductionSafe, assertRuntimeSafe } = require('./config/index')

function runtimeEnvVersion() {
  if (!wx.getAccountInfoSync) return 'unknown'
  try {
    const account = wx.getAccountInfoSync()
    return (account && account.miniProgram && account.miniProgram.envVersion) || 'unknown'
  } catch (error) {
    return 'unknown'
  }
}

App({
  globalData: {
    config: null,
    authToken: '',
    entitlement: null,
    serverOffsetMs: 0,
    pendingSave: false
  },

  onLaunch() {
    const config = getConfig()
    assertProductionSafe(config)
    assertRuntimeSafe(config, runtimeEnvVersion())
    this.globalData.config = config
  }
})
