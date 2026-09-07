const api = require('../../services/api')
const auth = require('../../services/auth')
const storage = require('../../services/storage')
const { historyJobView } = require('../../utils/history')
const { presentApiError } = require('../../utils/api-error')

Page({
  data: {
    jobs: [],
    loading: true,
    openingJobId: '',
    activeCount: 0,
    errorText: ''
  },

  onLoad() {
    this.pageVisible = true
  },

  onShow() {
    this.pageVisible = true
    this.refresh()
  },

  onHide() {
    this.pageVisible = false
    this.stopPolling()
  },

  onUnload() {
    this.pageVisible = false
    this.stopPolling()
  },

  onPullDownRefresh() {
    this.refresh(true)
  },

  stopPolling() {
    if (this.pollTimer) clearTimeout(this.pollTimer)
    this.pollTimer = null
  },

  async refresh(force = false) {
    if (this.refreshing && !force) return
    this.refreshing = true
    try {
      await auth.ensureAuth()
      const response = await api.listParseJobs(20)
      const jobs = (response.jobs || []).map(historyJobView)
      const active = jobs.filter((job) => job.active)
      storage.setParseJobs(active.map((job) => ({
        job_id: job.job_id,
        source_text: job.source_url,
        requested_quality: job.requested_quality,
        platform: job.platform,
        status: job.status,
        progress: job.progress,
        stage: job.stage
      })))
      this.setData({
        jobs,
        loading: false,
        activeCount: active.length,
        errorText: ''
      })
    } catch (error) {
      const presented = presentApiError(error)
      this.setData({ loading: false, errorText: presented.message })
    } finally {
      this.refreshing = false
      if (wx.stopPullDownRefresh) wx.stopPullDownRefresh()
      this.stopPolling()
      if (this.pageVisible && this.data.activeCount > 0) {
        this.pollTimer = setTimeout(() => this.refresh(), 1500)
      }
    }
  },

  async openJob(event) {
    const jobId = event.currentTarget.dataset.id
    const job = this.data.jobs.find((item) => item.job_id === jobId)
    if (!job || this.data.openingJobId) return
    if (job.active) {
      await this.refresh(true)
      return
    }
    if (!job.ready) {
      storage.setParseDraft({
        source_text: job.source_url,
        requested_quality: job.requested_quality || 'original'
      })
      wx.switchTab({ url: '/pages/index/index' })
      return
    }

    this.setData({ openingJobId: jobId })
    try {
      const response = await api.parseJob(jobId)
      if (!response.job || response.job.status !== 'ready' || !response.job.result) {
        await this.refresh(true)
        wx.showToast({ title: '结果已过期，请重新提取', icon: 'none' })
        return
      }
      const cached = storage.getCurrentResult()
      const preferredSourceId = storage.getSelectedSource(jobId) || (
        cached && cached.job_id === jobId ? cached.selected_source_id : ''
      )
      storage.setCurrentResult({
        ...response.job.result,
        job_id: jobId,
        source_text: response.job.source_url || job.source_url,
        requested_quality: response.job.result.requested_quality || job.requested_quality,
        // Keep a locally selected source when the history endpoint reissues
        // fresh capability URLs.  The result page will fall back only if the
        // server no longer returns that source.
        selected_source_id: preferredSourceId || response.job.result.selected_source_id
      })
      wx.navigateTo({ url: '/pages/result/result' })
    } catch (error) {
      const presented = presentApiError(error)
      wx.showModal({ title: presented.title, content: presented.message, showCancel: false })
    } finally {
      this.setData({ openingJobId: '' })
    }
  }
})
