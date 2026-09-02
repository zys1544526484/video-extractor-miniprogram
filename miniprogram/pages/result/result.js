const api = require('../../services/api')
const auth = require('../../services/auth')
const entitlement = require('../../services/entitlement')
const storage = require('../../services/storage')
const { createRewardedAdService } = require('../../services/ad')
const { createDownloadService } = require('../../services/download')
const { createIdempotencyKey } = require('../../utils/idempotency')
const { formatBytes, formatDuration } = require('../../utils/format')
const { entitlementView } = require('../../utils/time')
const { getConfig } = require('../../config/index')

Page({
  data: {
    result: null,
    state: 'loading',
    progress: 0,
    infoText: '',
    watermarkText: '媒体来源：未知',
    bannerAdUnitId: '',
    showBannerAd: false,
    mockMode: false,
    unlocking: false,
    saveButtonText: '保存视频'
  },

  onLoad() {
    const config = getConfig()
    this.adService = createRewardedAdService({ config })
    this.downloadService = createDownloadService({ config })
    try {
      this.adService.init()
    } catch (error) {
      if (config.APP_ENV === 'production') console.warn('激励广告初始化失败')
    }
    this.setData({
      bannerAdUnitId: config.BANNER_AD_UNIT_ID,
      showBannerAd: Boolean(config.BANNER_AD_UNIT_ID) || config.APP_ENV !== 'production',
      mockMode: config.MOCK_API
    })
    this.loadResult(storage.getCurrentResult())
  },

  onUnload() {
    if (this.adService) this.adService.destroy()
  },

  loadResult(result) {
    if (!result) {
      this.setData({ state: 'error' })
      wx.showModal({
        title: '结果已失效',
        content: '请返回首页重新提取。',
        showCancel: false,
        success: () => wx.navigateBack()
      })
      return
    }
    const sourceMap = {
      source_original: '媒体来源：公开原始资源',
      platform_watermarked: '媒体来源：平台公开水印版本',
      author_embedded: '媒体来源：作者已嵌入画面标识',
      unknown: '媒体来源：公开资源'
    }
    this.setData({
      result,
      state: 'ready',
      progress: 0,
      infoText: `${result.quality_label || '清晰度未知'} · ${formatDuration(result.duration_seconds)} · ${formatBytes(result.size_bytes)}`,
      watermarkText: sourceMap[result.watermark_status] || sourceMap.unknown,
      saveButtonText: '保存视频'
    })
  },

  async ensureFreshResult() {
    const result = this.data.result
    const app = getApp()
    const serverNow = Date.now() + (app.globalData.serverOffsetMs || 0)
    if (result && Date.parse(result.expires_at) > serverNow) return result
    if (!result || !result.source_text) throw new Error('结果已过期，请重新提取')
    this.setData({ state: 'loading' })
    const response = await api.parse(result.source_text)
    const refreshed = { ...response.result, source_text: result.source_text }
    storage.setCurrentResult(refreshed)
    this.loadResult(refreshed)
    return refreshed
  },

  async ensureDownloadEntitlement() {
    const value = await entitlement.refreshEntitlement()
    const app = getApp()
    const now = Date.now() + (app.globalData.serverOffsetMs || 0)
    if (entitlementView(value, now).entitled) return true

    const confirmed = await new Promise((resolve) => {
      wx.showModal({
        title: '解锁 24 小时下载',
        content: '完整观看一次广告后，可在 24 小时内保存视频。',
        confirmText: '观看广告',
        cancelText: '暂不',
        success: (result) => resolve(Boolean(result.confirm))
      })
    })
    if (!confirmed) return false

    let adResult
    try {
      adResult = await this.adService.show()
    } catch (error) {
      wx.showToast({ title: '广告暂时加载失败，请稍后重试', icon: 'none' })
      return false
    }
    if (!adResult.completed) {
      wx.showToast({ title: '需完整观看广告才能解锁下载', icon: 'none' })
      return false
    }
    await entitlement.completeAd(createIdempotencyKey())
    if (adResult.mock) wx.showToast({ title: '开发模式：已模拟完整观看', icon: 'none' })
    return true
  },

  async saveVideo() {
    if (this.saveInFlight || ['loading', 'downloading', 'saving'].includes(this.data.state)) return
    this.saveInFlight = true
    try {
      await auth.ensureAuth()
      const result = await this.ensureFreshResult()
      this.setData({ unlocking: true, saveButtonText: '检查下载权益…' })
      const entitled = await this.ensureDownloadEntitlement()
      if (!entitled) {
        this.setData({ unlocking: false, saveButtonText: '保存视频' })
        return
      }

      this.setData({ state: 'downloading', progress: 0, unlocking: false, saveButtonText: '下载中…' })
      const saved = await this.downloadService.downloadAndSave(result.download_url, (progress) => {
        this.setData({ progress, state: progress >= 100 ? 'saving' : 'downloading', saveButtonText: progress >= 100 ? '保存中…' : '下载中…' })
      })
      this.setData({ state: 'success', progress: 100, saveButtonText: '保存成功' })
      wx.showModal({
        title: saved.mock ? 'Mock 流程完成' : '保存成功',
        content: saved.mock ? '开发模式已模拟下载进度；没有写入系统相册。' : '视频已保存到系统相册。',
        showCancel: false
      })
    } catch (error) {
      this.setData({ state: 'error', unlocking: false, saveButtonText: '重新保存' })
      if (error.permissionDenied) {
        wx.showModal({
          title: '需要相册权限',
          content: '请在小程序设置中允许写入相册后重试。',
          confirmText: '去设置',
          success: (result) => {
            if (result.confirm) wx.openSetting()
          }
        })
      } else {
        wx.showModal({ title: '保存失败', content: error.message || '请稍后重试', showCancel: false })
      }
    } finally {
      this.saveInFlight = false
    }
  },

  extractAgain() {
    storage.clearCurrentResult()
    wx.navigateBack({ delta: 1 })
  },

  onBannerAdError() {
    if (getConfig().APP_ENV === 'production') this.setData({ showBannerAd: false })
  }
})
