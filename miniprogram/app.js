const { getConfig, assertProductionSafe } = require('./config/index')

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
    this.globalData.config = config
  }
})

