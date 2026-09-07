const { formatBytes } = require('./format')

const PLATFORM_LABELS = {
  bilibili: '哔哩哔哩',
  weibo: '微博',
  xiaohongshu: '小红书',
  douyin: '抖音',
  kuaishou: '快手',
  generic: '网页视频'
}

function platformLabel(value) {
  return PLATFORM_LABELS[value] || value || '视频'
}

function shortDate(value) {
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return ''
  const pad = (number) => String(number).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function historyJobView(job) {
  const value = job || {}
  const summary = value.summary || {}
  const active = value.status === 'queued' || value.status === 'processing'
  const ready = value.status === 'ready' && value.media_available
  const statusMap = {
    queued: '排队中',
    processing: '提取中',
    ready: ready ? '可继续下载' : '文件已过期',
    failed: '提取失败',
    cancelled: '已取消',
    expired: '文件已过期'
  }
  const error = value.error || {}
  const failureDetail = error.code
    ? `${error.code}：${error.message || '暂时无法完成提取'}`
    : (value.status === 'failed' ? (value.stage || '暂时无法完成提取') : '')
  return {
    ...value,
    active,
    ready,
    platform_label: platformLabel(value.platform),
    title: summary.title || (active ? '正在准备视频' : '视频记录'),
    detail: failureDetail || [summary.quality_label, formatBytes(summary.size_bytes)].filter(Boolean).join(' · '),
    status_label: statusMap[value.status] || '状态未知',
    action_label: ready ? '打开结果' : (active ? '刷新进度' : '再次提取'),
    created_label: shortDate(value.created_at)
  }
}

module.exports = { platformLabel, shortDate, historyJobView }
