const { getConfig } = require('../config/index')

function createRewardedAdService({ wxApi = wx, config = getConfig() } = {}) {
  let ad = null
  let closeHandler = null
  let errorHandler = null

  function init() {
    if (config.MOCK_REWARDED_AD) return null
    if (!config.REWARDED_AD_UNIT_ID) throw new Error('未配置激励视频广告位')
    if (!wxApi.createRewardedVideoAd) throw new Error('当前微信版本不支持激励视频广告')
    ad = wxApi.createRewardedVideoAd({ adUnitId: config.REWARDED_AD_UNIT_ID })
    return ad
  }

  async function show() {
    if (config.MOCK_REWARDED_AD) {
      await new Promise((resolve) => setTimeout(resolve, 450))
      return { completed: config.MOCK_AD_OUTCOME === 'completed', mock: true }
    }
    if (!ad) init()
    return new Promise(async (resolve, reject) => {
      closeHandler = (result) => {
        cleanupListeners()
        resolve({ completed: Boolean(result && result.isEnded), mock: false })
      }
      errorHandler = (error) => {
        cleanupListeners()
        reject(new Error((error && error.errMsg) || '广告暂时加载失败'))
      }
      ad.onClose(closeHandler)
      ad.onError(errorHandler)
      try {
        await ad.show()
      } catch (firstError) {
        try {
          await ad.load()
          await ad.show()
        } catch (error) {
          cleanupListeners()
          reject(new Error((error && error.errMsg) || '广告暂时加载失败'))
        }
      }
    })
  }

  function cleanupListeners() {
    if (!ad) return
    if (closeHandler && ad.offClose) ad.offClose(closeHandler)
    if (errorHandler && ad.offError) ad.offError(errorHandler)
    closeHandler = null
    errorHandler = null
  }

  function destroy() {
    cleanupListeners()
    if (ad && ad.destroy) ad.destroy()
    ad = null
  }

  return { init, show, destroy }
}

module.exports = { createRewardedAdService }

