const api = require('../../services/api')
const auth = require('../../services/auth')
const entitlement = require('../../services/entitlement')
const storage = require('../../services/storage')
const { getConfig } = require('../../config/index')
const { normalizeShareText, hasHttpUrl } = require('../../utils/input')
const { entitlementView } = require('../../utils/time')
const { HOME_TRANSITIONS, createStateMachine } = require('../../utils/state-machine')
const { presentApiError } = require('../../utils/api-error')
const { QUALITY_OPTIONS, normalizeRequestedQuality } = require('../../utils/quality')

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
    qualityOptions: QUALITY_OPTIONS,
    selectedQuality: 'original'
  },

  onLoad() {
    this.stateMachine = createStateMachine('idle', HOME_TRANSITIONS)
    const config = getConfig()
    this.setData({
      bannerAdUnitId: config.BANNER_AD_UNIT_ID,
      showBannerAd: Boolean(config.BANNER_AD_UNIT_ID) || config.APP_ENV !== 'production',
      mockMode: config.MOCK_API
    })
    this.refreshSession()
  },

  onShow() {
    const tabBar = this.getTabBar && this.getTabBar()
    if (tabBar) tabBar.setData({ selected: 0 })
    this.updateEntitlementLabel(storage.getEntitlement())
  },

  async refreshSession() {
    try {
      await auth.ensureAuth()
      const value = await entitlement.refreshEntitlement()
      this.updateEntitlementLabel(value)
    } catch (error) {
      this.updateEntitlementLabel(storage.getEntitlement())
    }
  },

  updateEntitlementLabel(value) {
    const app = getApp()
    const now = Date.now() + (app.globalData.serverOffsetMs || 0)
    this.setData({ entitlementLabel: entitlementView(value, now).label })
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

  selectQuality(event) {
    if (this.data.busy) return
    const selectedQuality = normalizeRequestedQuality(event.currentTarget.dataset.value)
    this.setData({ selectedQuality })
  },

  async startParse() {
    if (this.data.busy) return
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
      const response = await api.parse(inputText, this.data.selectedQuality)
      storage.setCurrentResult({
        ...response.result,
        source_text: inputText,
        requested_quality: response.result.requested_quality || this.data.selectedQuality
      })
      this.setState('idle')
      wx.navigateTo({ url: '/pages/result/result' })
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
