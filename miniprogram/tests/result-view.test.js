const test = require('node:test')
const assert = require('node:assert/strict')

const {
  safeSourceUrl,
  normalizeResult,
  selectSource,
  restorePreferredSource,
  copyableDownloadUrl,
  copyAllText
} = require('../utils/result-view')

test('normalizes legacy single-source results without losing the safe URL', () => {
  const result = normalizeResult({
    title: '旧缓存',
    quality_label: '原视频',
    size_bytes: 100,
    preview_url: 'https://api.example.com/api/v1/media/random/preview',
    download_url: 'https://api.example.com/api/v1/media/random/download'
  })

  assert.equal(result.sources.length, 1)
  assert.equal(result.sources[0].label, '源1')
  assert.equal(result.selected_source_id, 'source-1')
  assert.equal(copyableDownloadUrl(result), result.download_url)
})

test('switching source changes the actual media URLs and metadata', () => {
  const original = normalizeResult({
    title: '多源',
    sources: [
      {
        source_id: 'source-1',
        quality_label: '1080P H.264',
        size_bytes: 100,
        preview_url: 'https://api.example.com/api/v1/media/one/preview',
        download_url: 'https://api.example.com/api/v1/media/one/download'
      },
      {
        source_id: 'source-2',
        quality_label: '720P H.264',
        size_bytes: 70,
        preview_url: 'https://api.example.com/api/v1/media/two/preview',
        download_url: 'https://api.example.com/api/v1/media/two/download'
      }
    ]
  })
  const switched = selectSource(original, 'source-2')
  assert.equal(switched.selected_source_id, 'source-2')
  assert.equal(switched.preview_url, original.sources[1].preview_url)
  assert.equal(switched.download_url, original.sources[1].download_url)
  assert.equal(switched.quality_label, '720P H.264')
  assert.equal(switched.size_bytes, 70)
})

test('copy link rejects upstream URLs and copy all includes title and share text', () => {
  assert.equal(safeSourceUrl('https://video.example.com/original.mp4'), false)
  assert.equal(copyableDownloadUrl({ download_url: 'https://video.example.com/original.mp4' }), '')
  assert.equal(copyAllText({ title: '作品', share_text: '分享文案' }), '作品\n分享文案')
})

test('image data remains empty when the backend has no safe image URL', () => {
  const result = normalizeResult({ title: '无图', images: [{ image_id: 'cover', url: 'https://upstream.example/cover.jpg' }] })
  assert.deepEqual(result.images, [])
})

test('source 2 is restored after a token renewal while it remains available', () => {
  const renewed = normalizeResult({
    title: '多源',
    selected_source_id: 'source-1',
    sources: [
      { source_id: 'source-1', preview_url: 'https://api.example.com/api/v1/media/one/preview', download_url: 'https://api.example.com/api/v1/media/one/download' },
      { source_id: 'source-2', preview_url: 'https://api.example.com/api/v1/media/two/preview', download_url: 'https://api.example.com/api/v1/media/two/download' }
    ]
  })
  const restored = restorePreferredSource(renewed, 'source-2')
  assert.equal(restored.fallback, false)
  assert.equal(restored.result.selected_source_id, 'source-2')
  assert.equal(restored.result.download_url, renewed.sources[1].download_url)
})

test('source 2 falls back only when the renewed result no longer contains it', () => {
  const renewed = normalizeResult({
    title: '多源',
    sources: [
      { source_id: 'source-1', preview_url: 'https://api.example.com/api/v1/media/one/preview', download_url: 'https://api.example.com/api/v1/media/one/download' }
    ]
  })
  const restored = restorePreferredSource(renewed, 'source-2')
  assert.equal(restored.fallback, true)
  assert.equal(restored.result.selected_source_id, 'source-1')
})

test('pure image results do not synthesize a video source from top-level URLs', () => {
  const result = normalizeResult({
    media_type: 'image',
    title: '图片作品',
    preview_url: 'https://api.example.com/api/v1/media/image/preview',
    download_url: 'https://api.example.com/api/v1/media/image/download',
    images: [{ image_id: 'image-1', preview_url: 'https://api.example.com/api/v1/media/image/preview' }]
  })
  assert.deepEqual(result.sources, [])
  assert.equal(result.media_type, 'image')
  assert.equal(result.images.length, 1)
})
