const api = require('../../services/api')
const auth = require('../../services/auth')
const entitlement = require('../../services/entitlement')
const storage = require('../../services/storage')
const { createRewardedAdService } = require('../../services/ad')
const { createDownloadService } = require('../../services/download')
const { createIdempotencyKey } = require('../../utils/idempotency')
const { formatBytes, formatDuration } = require('../../utils/format')
const { entitlementView } = require('../../utils/time')
const { isTokenExpired } = require('../../utils/result-expiry')
const { getConfig } = require('../../config/index')
const {
  normalizeResult,
  selectSource,
  copyableDownloadUrl,
  copyAllText
} = require('../../utils/result-view')

const SOURCE_LABELS = {
  source_original: '媒体来源：公开原始资源',
  platform_watermarked: '媒体来源：平台公开水印版本',
  author_embedded: '媒体来源：作者已嵌入画面标识',
  unknown: '媒体来源：公开资源'
}

Page({
  data: {
    result: null,
    state: 'loading',
    progress: 0,
    infoText: '',
    watermarkText: '媒体来源：未知',
    activeTab: 'video',
    sourceOptions: [],
    selectedSourceId: '',
    selectedSourceLabel: '',
    selectedSourceSizeLabel: '',
    sourceSheetVisible: false,
    images: [],
    savingImageId: '',
    bannerAdUnitId: '',
    showBannerAd: false,
    mockMode: false,
    accessMode: 'free',
    unlocking: false,
    saveButtonText: '保存视频'
  },

  onLoad() {
    const config = getConfig()
    this.downloadService = createDownloadService({ config })
    if (config.DOWNLOAD_ACCESS_MODE === 'rewarded_ad') {
      this.adService = createRewardedAdService({ config })
      try {
        this.adService.init()
      } catch (error) {
        if (config.APP_ENV === 'production') console.warn('激励广告初始化失败')
      }
    }
    this.setData({
      bannerAdUnitId: config.BANNER_AD_UNIT_ID,
      showBannerAd: config.DOWNLOAD_ACCESS_MODE === 'rewarded_ad' && (Boolean(config.BANNER_AD_UNIT_ID) || config.APP_ENV !== 'production'),
      accessMode: config.DOWNLOAD_ACCESS_MODE,
      mockMode: config.MOCK_API
    })
    this.loadResult(storage.getCurrentResult())
  },

  onUnload() {
    if (this.adService) this.adService.destroy()
  },

  loadResult(value) {
    const result = normalizeResult(value)
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
    this.setData({
      result,
      state: 'ready',
      progress: 0,
      infoText: this.infoText(result),
      watermarkText: SOURCE_LABELS[result.watermark_status] || SOURCE_LABELS.unknown,
      sourceOptions: result.sources || [],
      selectedSourceId: result.selected_source_id || '',
      selectedSourceLabel: this.sourceLabel(result.selected_source_id || ''),
      selectedSourceSizeLabel: this.sourceSizeLabel(result),
      images: result.images || [],
      saveButtonText: '保存视频'
    })
  },

  infoText(result) {
    return `${result.quality_label || '清晰度未知'} · ${formatDuration(result.duration_seconds)} · ${formatBytes(result.size_bytes)}`
  },

  sourceLabel(sourceId) {
    const match = /^source-(\d+)$/.exec(String(sourceId || ''))
    return match ? `源${match[1]}` : '当前源'
  },

  sourceSizeLabel(result) {
    const source = (result.sources || []).find((item) => item.source_id === result.selected_source_id)
    return (source && source.size_label) || formatBytes(result.size_bytes)
  },

  async ensureFreshResult() {
    const result = normalizeResult(this.data.result)
    const app = getApp()
    const serverNow = Date.now() + (app.globalData.serverOffsetMs || 0)
    if (result && !isTokenExpired(result, serverNow)) return result
    if (!result || !result.source_text) throw new Error('结果已过期，请重新提取')
    this.setData({ state: 'loading' })
    if (result.job_id) {
      const existing = await api.parseJob(result.job_id)
      if (existing.job && existing.job.status === 'ready' && existing.job.result) {
        const renewed = normalizeResult({
          ...existing.job.result,
          job_id: result.job_id,
          source_text: existing.job.source_url || result.source_text,
          requested_quality: existing.job.result.requested_quality || result.requested_quality
        })
        storage.setCurrentResult(renewed)
        this.loadResult(renewed)
        return renewed
      }
    }
    const response = await api.parse(result.source_text, result.requested_quality || 'original')
    const refreshed = normalizeResult({
      ...response.result,
      job_id: response.job_id,
      source_text: result.source_text,
      requested_quality: response.result.requested_quality || result.requested_quality || 'original'
    })
    storage.setCurrentResult(refreshed)
    this.loadResult(refreshed)
    return refreshed
  },

  switchTab(event) {
    const tab = event.currentTarget.dataset.tab
    if (['video', 'images', 'title'].includes(tab)) this.setData({ activeTab: tab })
  },

  openSourceSheet() {
    if (this.data.sourceOptions.length < 2) return
    this.setData({ sourceSheetVisible: true })
  },

  closeSourceSheet() {
    this.setData({ sourceSheetVisible: false })
  },

  noop() {},

  selectSource(event) {
    if (this.data.state === 'downloading' || this.data.state === 'saving') return
    const sourceId = event.currentTarget.dataset.id
    const next = selectSource(this.data.result, sourceId)
    if (!next || next.selected_source_id === this.data.selectedSourceId) {
      this.closeSourceSheet()
      return
    }
    storage.setCurrentResult(next)
    this.setData({
      result: next,
      sourceOptions: next.sources,
      selectedSourceId: next.selected_source_id,
      selectedSourceLabel: this.sourceLabel(next.selected_source_id),
      selectedSourceSizeLabel: this.sourceSizeLabel(next),
      infoText: this.infoText(next),
      sourceSheetVisible: false
    })
  },

  copyCurrentLink() {
    const url = copyableDownloadUrl(this.data.result)
    if (!url) {
      wx.showToast({ title: '安全链接已失效，请重新提取', icon: 'none' })
      return
    }
    wx.setClipboardData({ data: url, success: () => wx.showToast({ title: '链接已复制', icon: 'success' }) })
  },

  copyTitle() {
    const title = String((this.data.result && this.data.result.title) || '')
    if (!title) return
    wx.setClipboardData({ data: title, success: () => wx.showToast({ title: '标题已复制', icon: 'success' }) })
  },

  copyAll() {
    const text = copyAllText(this.data.result)
    if (!text) return
    wx.setClipboardData({ data: text, success: () => wx.showToast({ title: '全部内容已复制', icon: 'success' }) })
  },

  async ensureDownloadEntitlement() {
    if (this.data.accessMode === 'free') return true
    const value = await entitlement.refreshEntitlement()
    const app = getApp()
    const now = Date.now() + (app.globalData.serverOffsetMs || 0)
    if (entitlementView(value, now).entitled) return true
    const confirmed = await new Promise((resolve) => {
      wx.showModal({
        title: '解锁 24 小时下载',
        content: '完整观看一次广告后，可在 24 小时内保存当前内容。',
        confirmText: '观看广告',
        cancelText: '暂不',
        success: (result) => resolve(Boolean(result.confirm))
      })
    })
    if (!confirmed) return false
    const attempt = await entitlement.startAdAttempt()
    if (!attempt.attempt_required && attempt.entitled) {
      entitlement.saveEntitlement(attempt)
      return true
    }
    if (!attempt.attempt_token) throw new Error('无法创建广告确认凭证，请稍后重试')
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
    await entitlement.completeAd(createIdempotencyKey(), attempt.attempt_token)
    if (adResult.mock) wx.showToast({ title: '开发模式：已模拟完整观看', icon: 'none' })
    return true
  },

  async saveVideo() {
    return this.saveCurrentVideo()
  },

  async saveCurrentVideo() {
    if (this.saveInFlight || ['loading', 'downloading', 'saving'].includes(this.data.state)) return
    this.saveInFlight = true
    try {
      await auth.ensureAuth()
      const result = await this.ensureFreshResult()
      this.setData({ unlocking: true, saveButtonText: this.data.accessMode === 'free' ? '准备下载…' : '检查下载权益…' })
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
      this.handleSaveError(error)
    } finally {
      this.saveInFlight = false
    }
  },

  async saveImage(event) {
    const imageId = event.currentTarget.dataset.id
    if (this.saveInFlight || this.data.savingImageId) return
    this.saveInFlight = true
    try {
      await auth.ensureAuth()
      await this.ensureFreshResult()
      const image = (this.data.images || []).find((item) => item.image_id === imageId)
      if (!image || !image.download_url) return
      const entitled = await this.ensureDownloadEntitlement()
      if (!entitled) {
        this.setData({ state: 'ready' })
        return
      }
      this.setData({ savingImageId: imageId, state: 'downloading', progress: 0 })
      const saved = await this.downloadService.downloadAndSaveImage(image.download_url, (progress) => {
        this.setData({ progress, state: progress >= 100 ? 'saving' : 'downloading' })
      })
      this.setData({ state: 'success', progress: 100 })
      wx.showModal({
        title: saved.mock ? 'Mock 流程完成' : '保存成功',
        content: saved.mock ? '开发模式已模拟图片保存；没有写入系统相册。' : '图片已保存到系统相册。',
        showCancel: false
      })
    } catch (error) {
      this.handleSaveError(error)
    } finally {
      this.saveInFlight = false
      this.setData({ savingImageId: '' })
    }
  },

  handleSaveError(error) {
    this.setData({ state: 'error', unlocking: false, savingImageId: '', saveButtonText: '重新保存' })
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
  },

  extractAgain() {
    storage.clearCurrentResult()
    wx.navigateBack({ delta: 1 })
  },

  onBannerAdError() {
    if (getConfig().APP_ENV === 'production') this.setData({ showBannerAd: false })
  }
})
