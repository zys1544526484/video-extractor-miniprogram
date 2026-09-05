const TOKEN_KEY = 'video_extractor_auth_token'
const ENTITLEMENT_KEY = 'video_extractor_download_entitlement'
const RESULT_KEY = 'video_extractor_current_result'
const PARSE_JOB_KEY = 'video_extractor_parse_job'
const PARSE_JOBS_KEY = 'video_extractor_parse_jobs'
const PARSE_DRAFT_KEY = 'video_extractor_parse_draft'
const SELECTED_SOURCES_KEY = 'video_extractor_selected_sources'

function getToken() {
  return wx.getStorageSync(TOKEN_KEY) || ''
}

function setToken(token) {
  wx.setStorageSync(TOKEN_KEY, token || '')
}

function clearToken() {
  wx.removeStorageSync(TOKEN_KEY)
}

function getEntitlement() {
  return wx.getStorageSync(ENTITLEMENT_KEY) || null
}

function setEntitlement(value) {
  wx.setStorageSync(ENTITLEMENT_KEY, value || null)
}

function setCurrentResult(result) {
  wx.setStorageSync(RESULT_KEY, result || null)
}

function getCurrentResult() {
  return wx.getStorageSync(RESULT_KEY) || null
}

function clearCurrentResult() {
  wx.removeStorageSync(RESULT_KEY)
}

function getSelectedSource(jobId) {
  if (!jobId) return ''
  const stored = wx.getStorageSync(SELECTED_SOURCES_KEY)
  const selected = stored && typeof stored === 'object' && !Array.isArray(stored) ? stored : {}
  return selected[jobId] || ''
}

function setSelectedSource(jobId, sourceId) {
  if (!jobId || !sourceId) return
  const stored = wx.getStorageSync(SELECTED_SOURCES_KEY)
  const selected = stored && typeof stored === 'object' && !Array.isArray(stored) ? stored : {}
  selected[jobId] = sourceId
  wx.setStorageSync(SELECTED_SOURCES_KEY, selected)
}

function setParseJob(job) {
  if (!job) {
    clearParseJobs()
    return
  }
  upsertParseJob(job)
}

function getParseJob() {
  return getParseJobs()[0] || ''
}

function clearParseJob() {
  clearParseJobs()
}

function getParseJobs() {
  const stored = wx.getStorageSync(PARSE_JOBS_KEY)
  if (Array.isArray(stored)) return stored.filter((item) => item && item.job_id)
  const legacy = wx.getStorageSync(PARSE_JOB_KEY)
  if (!legacy || !legacy.job_id) return []
  const jobs = [legacy]
  wx.setStorageSync(PARSE_JOBS_KEY, jobs)
  wx.removeStorageSync(PARSE_JOB_KEY)
  return jobs
}

function setParseJobs(jobs) {
  const normalized = Array.isArray(jobs)
    ? jobs.filter((item) => item && item.job_id).slice(0, 10)
    : []
  wx.setStorageSync(PARSE_JOBS_KEY, normalized)
  wx.removeStorageSync(PARSE_JOB_KEY)
  return normalized
}

function upsertParseJob(job) {
  if (!job || !job.job_id) return getParseJobs()
  const jobs = getParseJobs().filter((item) => item.job_id !== job.job_id)
  return setParseJobs([{ ...job }, ...jobs])
}

function removeParseJob(jobId) {
  return setParseJobs(getParseJobs().filter((item) => item.job_id !== jobId))
}

function clearParseJobs() {
  wx.removeStorageSync(PARSE_JOBS_KEY)
  wx.removeStorageSync(PARSE_JOB_KEY)
}

function setParseDraft(draft) {
  wx.setStorageSync(PARSE_DRAFT_KEY, draft || null)
}

function takeParseDraft() {
  const draft = wx.getStorageSync(PARSE_DRAFT_KEY) || null
  wx.removeStorageSync(PARSE_DRAFT_KEY)
  return draft
}

module.exports = {
  getToken,
  setToken,
  clearToken,
  getEntitlement,
  setEntitlement,
  setCurrentResult,
  getCurrentResult,
  clearCurrentResult,
  getSelectedSource,
  setSelectedSource,
  setParseJob,
  getParseJob,
  clearParseJob,
  getParseJobs,
  setParseJobs,
  upsertParseJob,
  removeParseJob,
  clearParseJobs,
  setParseDraft,
  takeParseDraft
}
