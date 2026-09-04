const { formatBytes, formatDuration } = require('./format')

function safeSourceUrl(url) {
  const value = String(url || '')
  return /^https?:\/\/[^/]+\/api\/v1\/media\/[^/]+\/(?:preview|download)$/.test(value) ||
    /^\/assets\/[A-Za-z0-9._/-]+(?:\?[^\s]*)?$/.test(value)
}

function normalizeResult(result) {
  if (!result) return null
  const normalized = { ...result }
  // Older cached results only contain top-level media URLs. Convert them to source-1.
  const rawSources = Array.isArray(result.sources) && result.sources.length
    ? result.sources
    : (result.media_type !== 'image' && (result.preview_url || result.download_url) ? [{
        source_id: 'source-1',
        quality_label: result.quality_label,
        size_bytes: result.size_bytes,
        mime_type: 'video/mp4',
        preview_url: result.preview_url,
        download_url: result.download_url,
        expires_at: result.expires_at,
        media_expires_at: result.media_expires_at
      }] : [])
  normalized.sources = rawSources.map((source, index) => ({
    ...source,
    source_id: source.source_id || `source-${index + 1}`,
    label: `源${index + 1}`,
    quality_label: source.quality_label || result.quality_label || '清晰度未知',
    size_bytes: source.size_bytes == null ? result.size_bytes : source.size_bytes,
    size_label: formatBytes(source.size_bytes == null ? result.size_bytes : source.size_bytes)
  }))
  normalized.images = (Array.isArray(result.images) ? result.images : []).filter((item) => item && item.preview_url)
  normalized.share_text = result.share_text || [result.title, result.canonical_url || result.source_url].filter(Boolean).join('\n')
  normalized.selected_source_id = result.selected_source_id || (normalized.sources[0] && normalized.sources[0].source_id) || ''
  const selected = normalized.sources.find((item) => item.source_id === normalized.selected_source_id) || normalized.sources[0]
  if (selected) {
    normalized.selected_source_id = selected.source_id
    normalized.preview_url = selected.preview_url || normalized.preview_url || ''
    normalized.download_url = selected.download_url || normalized.download_url || ''
    normalized.quality_label = selected.quality_label || normalized.quality_label
    normalized.size_bytes = selected.size_bytes == null ? normalized.size_bytes : selected.size_bytes
    normalized.expires_at = selected.expires_at || normalized.expires_at
    normalized.media_expires_at = selected.media_expires_at || normalized.media_expires_at
  }
  // These fields are never needed by the UI and must not accidentally be copied or logged.
  delete normalized.upstream_media_url
  delete normalized.temporary_file
  delete normalized.required_headers
  return normalized
}

function selectSource(result, sourceId) {
  const normalized = normalizeResult(result)
  if (!normalized) return null
  const selected = normalized.sources.find((item) => item.source_id === sourceId)
  if (!selected) return normalized
  return normalizeResult({ ...normalized, selected_source_id: selected.source_id })
}

function restorePreferredSource(result, preferredSourceId) {
  const normalized = normalizeResult(result)
  if (!normalized) return { result: null, fallback: false }
  if (!preferredSourceId || normalized.media_type === 'image') {
    return { result: normalized, fallback: false }
  }
  const preferred = normalized.sources.find((item) => item.source_id === preferredSourceId)
  if (preferred) return { result: selectSource(normalized, preferredSourceId), fallback: false }
  // A non-empty source list that no longer contains the user's choice means
  // that source has genuinely expired/been removed.  The caller can notify the
  // user before using the first remaining source.
  if (normalized.sources.length) return { result: normalized, fallback: true }
  return { result: normalized, fallback: false }
}

function sourceInfo(source) {
  return `${(source && source.quality_label) || '清晰度未知'} · ${formatDuration(source && source.duration_seconds)} · ${formatBytes(source && source.size_bytes)}`
}

function copyableDownloadUrl(result) {
  const normalized = normalizeResult(result)
  const url = normalized && normalized.download_url
  return safeSourceUrl(url) ? url : ''
}

function copyAllText(result) {
  const normalized = normalizeResult(result)
  if (!normalized) return ''
  const share = String(normalized.share_text || '').trim()
  if (share && normalized.title && (share === normalized.title || share.startsWith(`${normalized.title}\n`))) return share
  return [normalized.title, share].filter(Boolean).join('\n').trim()
}

module.exports = {
  safeSourceUrl,
  normalizeResult,
  selectSource,
  restorePreferredSource,
  sourceInfo,
  copyableDownloadUrl,
  copyAllText
}
