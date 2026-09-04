const api = require('../../services/api')
const auth = require('../../services/auth')
const entitlement = require('../../services/entitlement')
const storage = require('../../services/storage')
const { getConfig } = require('../../config/index')
const { normalizeShareText, hasHttpUrl } = require('../../utils/input')
const { entitlementView } = require('../../utils/time')
const { HOME_TRANSITIONS, createStateMachine } = require('../../utils/state-machine')
const { presentApiError } = require('../../utils/api-error')
const { createOperationKey } = require('../../utils/idempotency')
const { platformLabel } = require('../../utils/history')

const BUTTON_LABELS = {
  idle: '开始提取',
  checking: '检查链接…',
  parsing: '提取中…',
  error: '重新提取'
}

Page({
  data: {
    inputText: '',
    charCount: 0,
    state: 'idle',
    buttonText: BUTTON_LABELS.idle,
    busy: false,
    entitlementLabel: '观看广告可解锁 24 小时下载',
    bannerAdUnitId: '',
    showBannerAd: false,
    mockMode: false,
    accessMode: 'free',
    parseProgress: 0,
    parseStage: '',
    activeJobs: [],
    activeJobCount: 0,
    atJobLimit: false
  },

  onLoad() {
    this.pageVisible = true
    this.stateMachine = createStateMachine('idle', HOME_TRANSITIONS)
    const config = getConfig()
    this.setData({
      bannerAdUnitId: config.BANNER_AD_UNIT_ID,
      showBannerAd: config.DOWNLOAD_ACCESS_MODE === 'rewarded_ad' && (Boolean(config.BANNER_AD_UNIT_ID) || config.APP_ENV !== 'production'),
      accessMode: config.DOWNLOAD_ACCESS_MODE,
      mockMode: config.MOCK_API
    })
    this.refreshSession()
  },

  onUnload() {
    this.pageVisible = false
    this.stopJobPolling()
  },

  onHide() {
    this.pageVisible = false
    this.stopJobPolling()
  },

  onShow() {
    this.pageVisible = true
    const tabBar = this.getTabBar && this.getTabBar()
    if (tabBar) tabBar.setData({ selected: 0 })
    this.updateEntitlementLabel(storage.getEntitlement())
    this.loadDraft()
    if (this.sessionReady) this.refreshActiveJobs()
  },

  async refreshSession() {
    try {
      await auth.ensureAuth()
      this.sessionReady = true
      const value = await entitlement.refreshEntitlement()
      this.updateEntitlementLabel(value)
      await this.refreshActiveJobs()
    } catch (error) {
      this.updateEntitlementLabel(storage.getEntitlement())
    }
  },

  updateEntitlementLabel(value) {
    const app = getApp()
    const now = Date.now() + (app.globalData.serverOffsetMs || 0)
    const view = entitlementView(value, now)
    this.setData({ entitlementLabel: view.label, accessMode: view.accessMode || this.data.accessMode })
  },

  loadDraft() {
    if (this.data.inputText) return
    const draft = storage.takeParseDraft()
    if (!draft || !draft.source_text) return
    const inputText = normalizeShareText(draft.source_text)
    this.setData({
      inputText,
      charCount: inputText.length,
    })
  },

  setState(state) {
    if (!this.stateMachine) this.stateMachine = createStateMachine(this.data.state || 'idle', HOME_TRANSITIONS)
    this.stateMachine.transition(state)
    this.setData({
      state,
      buttonText: BUTTON_LABELS[state] || BUTTON_LABELS.idle,
      busy: state === 'checking' || state === 'parsing'
    })
  },

  onInput(event) {
    const inputText = String(event.detail.value || '').slice(0, 5000)
    this.setData({ inputText, charCount: inputText.length })
  },

  onBlur() {
    const inputText = normalizeShareText(this.data.inputText)
    this.setData({ inputText, charCount: inputText.length })
  },

  async pasteClipboard() {
    try {
      const result = await new Promise((resolve, reject) => {
        wx.getClipboardData({ success: resolve, fail: reject })
      })
      const inputText = normalizeShareText(result.data)
      this.setData({ inputText, charCount: inputText.length })
      wx.showToast({ title: '已粘贴', icon: 'success' })
    } catch (error) {
      wx.showToast({ title: '无法读取剪贴板', icon: 'none' })
    }
  },

  async startParse() {
    if (this.data.busy) return
    if (this.data.atJobLimit) {
      wx.showToast({ title: '最多同时提取 2 个视频', icon: 'none' })
      return
    }
    const inputText = normalizeShareText(this.data.inputText)
    if (!inputText) {
      wx.showToast({ title: '请先粘贴分享文案或链接', icon: 'none' })
      return
    }
    if (!hasHttpUrl(inputText)) {
      wx.showToast({ title: '未识别到有效链接', icon: 'none' })
      return
    }

    this.setState('checking')
    try {
      await auth.ensureAuth()
      this.setState('parsing')
      const created = await api.createParse(
        inputText,
        'original',
        createOperationKey('parse')
      )
      const jobId = created.job.job_id
      storage.setParseJob({
        job_id: jobId,
        source_text: inputText,
        requested_quality: 'original',
        platform: created.job.platform,
        status: created.job.status,
        progress: created.job.progress || 0,
        stage: created.job.stage || '等待处理'
      })
      this.setData({ inputText: '', charCount: 0, parseProgress: 0, parseStage: '' })
      this.setState('idle')
      await this.refreshActiveJobs()
      wx.showToast({ title: '已加入提取任务', icon: 'success' })
    } catch (error) {
      this.setState('error')
      const presented = presentApiError(error)
      wx.showModal({
        title: presented.title,
        content: `${presented.message}${error.requestId ? `\n请求编号：${error.requestId}` : ''}`,
        showCancel: false
      })
    }
  },

  stopJobPolling() {
    if (this.jobPollTimer) clearTimeout(this.jobPollTimer)
    this.jobPollTimer = null
  },

  async refreshActiveJobs() {
    if (this.refreshJobsInFlight) return
    this.refreshJobsInFlight = true
    const localJobs = storage.getParseJobs()
    const localById = new Map(localJobs.map((job) => [job.job_id, job]))
    try {
      const response = await api.listParseJobs(20)
      const activeJobs = (response.jobs || [])
        .filter((job) => job.status === 'queued' || job.status === 'processing')
        .slice(0, 2)
        .map((job) => {
          const local = localById.get(job.job_id) || {}
          return {
            ...local,
            ...job,
            platform_label: platformLabel(job.platform),
            source_text: local.source_text || job.source_url || '',
            progress: job.progress || 0,
            stage: job.stage || '处理中'
          }
        })
      const activeIds = new Set(activeJobs.map((job) => job.job_id))
      const completed = (response.jobs || []).some((job) => (
        localById.has(job.job_id) && !activeIds.has(job.job_id) && job.status === 'ready'
      ))
      storage.setParseJobs(activeJobs)
      this.setData({
        activeJobs,
        activeJobCount: activeJobs.length,
        atJobLimit: activeJobs.length >= 2
      })
      if (completed) wx.showToast({ title: '提取完成，请到记录中打开', icon: 'none' })
    } catch (error) {
      const activeJobs = localJobs.slice(0, 2).map((job) => ({
        ...job,
        platform_label: platformLabel(job.platform),
        progress: job.progress || 0,
        stage: job.stage || '等待网络恢复'
      }))
      this.setData({
        activeJobs,
        activeJobCount: activeJobs.length,
        atJobLimit: activeJobs.length >= 2
      })
    } finally {
      this.refreshJobsInFlight = false
      this.stopJobPolling()
      if (this.pageVisible && this.data.activeJobCount > 0) {
        this.jobPollTimer = setTimeout(() => this.refreshActiveJobs(), 1500)
      }
    }
  },

  openHistory() {
    wx.navigateTo({ url: '/pages/history/history' })
  },

  openTutorial() {
    wx.navigateTo({ url: '/pages/tutorial/tutorial' })
  },

  openFaq() {
    wx.navigateTo({ url: '/pages/faq/faq' })
  },

  openMine() {
    wx.switchTab({ url: '/pages/mine/mine' })
  },

  onBannerAdError() {
    const config = getConfig()
    if (config.APP_ENV === 'production') this.setData({ showBannerAd: false })
  }
})
