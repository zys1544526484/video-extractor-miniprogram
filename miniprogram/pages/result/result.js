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
  restorePreferredSource,
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
    jobId: '',
    progress: 0,
    parseStage: '等待任务状态',
    parseErrorCode: '',
    parseErrorMessage: '',
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

  onLoad(options = {}) {
    this.pageVisible = true
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
    const jobId = String(options.job_id || '')
    if (jobId) {
      this.setData({ jobId })
      this.startJobPolling(jobId)
    } else {
      this.loadResult(storage.getCurrentResult())
    }
  },

  onShow() {
    this.pageVisible = true
    if (this.data.jobId && (this.data.state === 'loading' || !this.data.result)) {
      this.startJobPolling(this.data.jobId)
    }
  },

  onHide() {
    this.pageVisible = false
    this.stopJobPolling()
  },

  onUnload() {
    this.pageVisible = false
    this.stopJobPolling()
    if (this.adService) this.adService.destroy()
  },

  stopJobPolling() {
    if (this.jobPollTimer) clearTimeout(this.jobPollTimer)
    this.jobPollTimer = null
    this.pollGeneration = (this.pollGeneration || 0) + 1
  },

  updateJobProgress(job) {
    if (!job) return
    this.lastJob = job
    const progress = Math.max(0, Math.min(100, Number(job.progress) || 0))
    const local = {
      job_id: job.job_id || this.data.jobId,
      source_text: job.source_url || (this.data.result && this.data.result.source_text) || '',
      requested_quality: job.requested_quality || 'original',
      platform: job.platform,
      status: job.status,
      progress,
      stage: job.stage || '处理中',
      error: job.error
    }
    if (local.job_id) storage.upsertParseJob(local)
    this.setData({
      state: job.status === 'ready' ? 'ready' : 'loading',
      progress,
      parseStage: job.stage || '处理中',
      parseErrorCode: '',
      parseErrorMessage: ''
    })
  },

  async startJobPolling(jobId) {
    if (!jobId || this.pollInFlight) return
    this.pollInFlight = true
    this.pageVisible = this.pageVisible !== false
    const generation = this.pollGeneration || 0
    this.setData({
      jobId,
      result: null,
      state: 'loading',
      progress: 0,
      parseStage: '正在连接提取任务',
      parseErrorCode: '',
      parseErrorMessage: ''
    })
    try {
      await auth.ensureAuth()
      const result = await api.waitForParseJob(
        jobId,
        (job) => this.updateJobProgress(job),
        {
          shouldContinue: () => this.pageVisible !== false && generation === (this.pollGeneration || 0)
        }
      )
      if (!result || generation !== (this.pollGeneration || 0)) return
      const job = this.lastJob || {}
      const normalized = normalizeResult({
        ...result,
        job_id: jobId,
        source_text: job.source_url || '',
        requested_quality: result.requested_quality || job.requested_quality || 'original'
      })
      storage.setParseJob({
        job_id: jobId,
        source_text: job.source_url || '',
        requested_quality: normalized.requested_quality,
        platform: job.platform || normalized.platform,
        status: 'ready',
        progress: 100,
        stage: '处理完成'
      })
      storage.setCurrentResult(normalized)
      this.loadResult(normalized)
    } catch (error) {
      if (generation !== (this.pollGeneration || 0) || error.code === 'JOB_CANCELLED') return
      this.showJobFailure(error, this.lastJob)
    } finally {
      this.pollInFlight = false
    }
  },

  showJobFailure(error, job) {
    const detail = (job && job.error) || {}
    const code = error.code || detail.code || 'PARSE_FAILED'
    const message = error.message || detail.message || '暂时无法完成提取'
    const jobId = (job && job.job_id) || this.data.jobId
    if (jobId) {
      storage.upsertParseJob({
        job_id: jobId,
        source_text: (job && job.source_url) || '',
        requested_quality: (job && job.requested_quality) || 'original',
        platform: job && job.platform,
        status: (job && job.status) || 'failed',
        progress: (job && job.progress) || 0,
        stage: (job && job.stage) || '处理失败',
        error: { code, message, retryable: Boolean(error.retryable || detail.retryable) }
      })
    }
    this.setData({
      result: null,
      state: 'error',
      progress: (job && job.progress) || 0,
      parseStage: (job && job.stage) || '处理失败',
      parseErrorCode: code,
      parseErrorMessage: message
    })
  },

  loadResult(value) {
    const normalized = normalizeResult(value)
    const preferredSourceId = normalized && normalized.job_id
      ? storage.getSelectedSource(normalized.job_id)
      : ''
    const restored = restorePreferredSource(normalized, preferredSourceId)
    const result = restored.result
    if (!result) {
      this.setData({
        state: 'error',
        parseErrorCode: 'RESULT_NOT_FOUND',
        parseErrorMessage: '结果已失效，请返回首页重新提取。'
      })
      return
    }
    if (restored.fallback) this.notifySourceFallback(result)
    this.setData({
      result,
      state: 'ready',
      jobId: result.job_id || this.data.jobId || '',
      progress: 0,
      parseStage: '处理完成',
      parseErrorCode: '',
      parseErrorMessage: '',
      infoText: this.infoText(result),
      watermarkText: SOURCE_LABELS[result.watermark_status] || SOURCE_LABELS.unknown,
      activeTab: result.media_type === 'image' ? 'images' : 'video',
      sourceOptions: result.sources || [],
      selectedSourceId: result.selected_source_id || '',
      selectedSourceLabel: this.sourceLabel(result.selected_source_id || '', result.sources),
      selectedSourceSizeLabel: this.sourceSizeLabel(result),
      images: result.images || [],
      saveButtonText: '保存视频'
    })
  },

  infoText(result) {
    return `${result.quality_label || '清晰度未知'} · ${formatDuration(result.duration_seconds)} · ${formatBytes(result.size_bytes)}`
  },

  sourceLabel(sourceId, sources) {
    const list = sources || this.data.sourceOptions || []
    const index = list.findIndex((item) => item.source_id === sourceId)
    return index >= 0 ? `源${index + 1}` : '当前源'
  },

  sourceSizeLabel(result) {
    const source = (result.sources || []).find((item) => item.source_id === result.selected_source_id)
    return (source && source.size_label) || formatBytes(result.size_bytes)
  },

  async ensureFreshResult() {
    const result = normalizeResult(this.data.result)
    const preferredSourceId = result && (
      storage.getSelectedSource(result.job_id) || result.selected_source_id
    )
    const app = getApp()
    const serverNow = Date.now() + (app.globalData.serverOffsetMs || 0)
    if (result && !isTokenExpired(result, serverNow)) return result
    if (!result || !result.source_text) throw new Error('结果已过期，请重新提取')
    this.setData({ state: 'loading' })
    if (result.job_id) {
      const existing = await api.parseJob(result.job_id)
      if (existing.job && existing.job.status === 'ready' && existing.job.result) {
        const renewedRaw = normalizeResult({
          ...existing.job.result,
          job_id: result.job_id,
          source_text: existing.job.source_url || result.source_text,
          requested_quality: existing.job.result.requested_quality || result.requested_quality
        })
        const restored = restorePreferredSource(renewedRaw, preferredSourceId)
        const renewed = restored.result
        if (restored.fallback) this.notifySourceFallback(renewed)
        storage.setCurrentResult(renewed)
        this.loadResult(renewed)
        return renewed
      }
    }
    const response = await api.parse(result.source_text, result.requested_quality || 'original')
    const refreshedRaw = normalizeResult({
      ...response.result,
      job_id: response.job_id,
      source_text: result.source_text,
      requested_quality: response.result.requested_quality || result.requested_quality || 'original'
    })
    const restored = restorePreferredSource(refreshedRaw, preferredSourceId)
    const refreshed = restored.result
    if (restored.fallback) this.notifySourceFallback(refreshed)
    storage.setCurrentResult(refreshed)
    this.loadResult(refreshed)
    return refreshed
  },

  notifySourceFallback(result) {
    if (result && result.job_id && result.selected_source_id) {
      storage.setSelectedSource(result.job_id, result.selected_source_id)
    }
    wx.showModal({
      title: '视频源已过期',
      content: '原选择的视频源已过期，已切换到当前可用源。',
      showCancel: false
    })
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
    if (next.job_id && next.selected_source_id) {
      storage.setSelectedSource(next.job_id, next.selected_source_id)
      api.selectParseSource(next.job_id, next.selected_source_id).catch(() => {})
    }
    this.setData({
      result: next,
      sourceOptions: next.sources,
      selectedSourceId: next.selected_source_id,
      selectedSourceLabel: this.sourceLabel(next.selected_source_id, next.sources),
      selectedSourceSizeLabel: this.sourceSizeLabel(next),
      infoText: this.infoText(next),
      sourceSheetVisible: false
    })
  },

  async copyCurrentLink() {
    if (this.copyInFlight) return
    this.copyInFlight = true
    try {
      const result = await this.ensureFreshResult()
      const url = copyableDownloadUrl(result)
      if (!url) throw new Error('安全链接已失效，请重新提取')
      await new Promise((resolve, reject) => {
        wx.setClipboardData({ data: url, success: resolve, fail: reject })
      })
      wx.showToast({ title: '链接已复制', icon: 'success' })
    } catch (error) {
      wx.showToast({ title: error.message || '安全链接刷新失败，请稍后重试', icon: 'none' })
    } finally {
      this.copyInFlight = false
    }
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
