const QUALITY_OPTIONS = Object.freeze([
  { value: 'original', label: '原视频', note: '最高画质' },
  { value: '720p', label: '720P', note: '高清' },
  { value: '540p', label: '540P', note: '省流量' }
])

const QUALITY_VALUES = new Set(QUALITY_OPTIONS.map((item) => item.value))

function normalizeRequestedQuality(value) {
  return QUALITY_VALUES.has(value) ? value : 'original'
}

function qualityOption(value) {
  const normalized = normalizeRequestedQuality(value)
  return QUALITY_OPTIONS.find((item) => item.value === normalized)
}

module.exports = { QUALITY_OPTIONS, normalizeRequestedQuality, qualityOption }
