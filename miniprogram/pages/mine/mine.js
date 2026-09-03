const auth = require('../../services/auth')
const entitlement = require('../../services/entitlement')
const storage = require('../../services/storage')
const { entitlementView } = require('../../utils/time')

Page({
  data: {
    entitled: false,
    entitlementLabel: '当前可免费保存',
    expiresLabel: '无需观看广告，无到期时间',
    loading: false
  },

  onShow() {
    const tabBar = this.getTabBar && this.getTabBar()
    if (tabBar) tabBar.setData({ selected: 1 })
    this.renderEntitlement(storage.getEntitlement())
    this.refresh()
  },

  renderEntitlement(value) {
    const app = getApp()
    const view = entitlementView(value, Date.now() + (app.globalData.serverOffsetMs || 0))
    this.setData({
      entitled: view.entitled,
      entitlementLabel: view.accessMode === 'free' ? '当前可免费保存' : (view.entitled ? '下载权益有效' : '下载权益未解锁'),
      expiresLabel: view.accessMode === 'free' ? view.expiresLabel : (view.entitled ? `有效期至 ${view.expiresLabel}` : '在结果页保存时观看广告即可解锁')
    })
  },

  async refresh() {
    if (this.data.loading) return
    this.setData({ loading: true })
    try {
      await auth.ensureAuth()
      const value = await entitlement.refreshEntitlement()
      this.renderEntitlement(value)
    } catch (error) {
      this.renderEntitlement(storage.getEntitlement())
    } finally {
      this.setData({ loading: false })
    }
  },

  openTutorial() {
    wx.navigateTo({ url: '/pages/tutorial/tutorial' })
  },

  openFaq() {
    wx.navigateTo({ url: '/pages/faq/faq' })
  },

  showPrivacy() {
    wx.showModal({
      title: '隐私与存储说明',
      content: '仅保存认证所需标识。部分媒体可能短时缓存，并在任务结束或过期后自动清理。',
      showCancel: false
    })
  },

  onShareAppMessage() {
    return { title: '视频提取｜常见公开视频链接解析工具', path: '/pages/index/index' }
  }
})
