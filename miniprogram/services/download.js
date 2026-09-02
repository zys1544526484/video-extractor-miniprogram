const { getConfig } = require('../config/index')
const storage = require('./storage')

function createDownloadService({ wxApi = wx, config = getConfig() } = {}) {
  async function mockDownload(onProgress) {
    for (const progress of [8, 22, 41, 63, 82, 100]) {
      await new Promise((resolve) => setTimeout(resolve, 90))
      if (onProgress) onProgress(progress)
    }
    return { mock: true, saved: false }
  }

  function download(url, onProgress) {
    return new Promise((resolve, reject) => {
      const task = wxApi.downloadFile({
        url,
        timeout: 600000,
        header: { Authorization: `Bearer ${storage.getToken()}` },
        success(response) {
          if (response.statusCode === 200 || response.statusCode === 206) resolve(response.tempFilePath)
          else reject(new Error(`下载失败（HTTP ${response.statusCode}）`))
        },
        fail(error) {
          reject(new Error(error.errMsg || '下载失败'))
        }
      })
      if (task && task.onProgressUpdate && onProgress) {
        task.onProgressUpdate((event) => onProgress(event.progress || 0))
      }
    })
  }

  function save(filePath) {
    return new Promise((resolve, reject) => {
      wxApi.saveVideoToPhotosAlbum({
        filePath,
        success: resolve,
        fail(error) {
          const result = new Error(error.errMsg || '保存到相册失败')
          result.permissionDenied = /auth deny|authorize:fail|permission/i.test(error.errMsg || '')
          reject(result)
        }
      })
    })
  }

  async function downloadAndSave(url, onProgress) {
    if (config.MOCK_API) return mockDownload(onProgress)
    const filePath = await download(url, onProgress)
    await save(filePath)
    return { mock: false, saved: true, filePath }
  }

  return { downloadAndSave }
}

module.exports = { createDownloadService }
