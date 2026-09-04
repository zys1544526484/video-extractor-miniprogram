const fs = require('node:fs')
const path = require('node:path')
const { execFileSync } = require('node:child_process')

const root = path.resolve(__dirname, '..')
const mini = path.join(root, 'miniprogram')
const failures = []
const productionCheck = process.argv.includes('--production')

function fail(message) {
  failures.push(message)
}

function readJson(file) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'))
  } catch (error) {
    fail(`${path.relative(root, file)} JSON 无效：${error.message}`)
    return null
  }
}

const allFiles = []
function walk(directory) {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const file = path.join(directory, entry.name)
    if (entry.isDirectory()) walk(file)
    else allFiles.push(file)
  }
}
walk(mini)

for (const file of allFiles.filter((item) => item.endsWith('.json'))) readJson(file)
for (const file of allFiles.filter((item) => item.endsWith('.js'))) {
  try {
    execFileSync(process.execPath, ['--check', file], { stdio: 'pipe' })
  } catch (error) {
    fail(`${path.relative(root, file)} JavaScript 语法无效`)
  }
}

const appJson = readJson(path.join(mini, 'app.json'))
if (appJson) {
  for (const page of appJson.pages || []) {
    for (const ext of ['.js', '.json', '.wxml', '.wxss']) {
      const file = path.join(mini, `${page}${ext}`)
      if (!fs.existsSync(file)) fail(`app.json 页面文件缺失：${page}${ext}`)
    }
  }
  for (const item of (appJson.tabBar && appJson.tabBar.list) || []) {
    if (!(appJson.pages || []).includes(item.pagePath)) fail(`tabBar 页面未注册：${item.pagePath}`)
  }
  if (appJson.tabBar && appJson.tabBar.custom) {
    for (const ext of ['.js', '.json', '.wxml', '.wxss']) {
      if (!fs.existsSync(path.join(mini, `custom-tab-bar/index${ext}`))) fail(`自定义 tabBar 缺失 index${ext}`)
    }
  }
}

for (const file of allFiles.filter((item) => item.endsWith('.wxml'))) {
  const source = fs.readFileSync(file, 'utf8')
  for (const match of source.matchAll(/(?:src|poster)="(\/assets\/[^"{]+)"/g)) {
    const asset = path.join(mini, match[1].replace(/^\//, ''))
    if (!fs.existsSync(asset)) fail(`${path.relative(root, file)} 引用缺失资源：${match[1]}`)
  }
}

const combined = allFiles
  .filter((item) => /\.(?:js|json|wxml|wxss)$/.test(item))
  .map((item) => fs.readFileSync(item, 'utf8'))
  .join('\n')
if (/WECHAT_APP_SECRET\s*[:=]\s*['"][^'"]+/.test(combined)) fail('小程序代码疑似包含 AppSecret')

if (productionCheck) {
  try {
    const { getConfig, assertProductionSafe, assertRuntimeSafe } = require(path.join(mini, 'config'))
    const useSynthetic = process.env.MINIPROGRAM_VALIDATE_SYNTHETIC === '1'
    const config = useSynthetic
      ? {
          APP_ENV: process.env.VALIDATE_PRODUCTION_APP_ENV || 'production',
          API_BASE_URL: process.env.VALIDATE_PRODUCTION_API_BASE_URL || 'https://media-api.valid-domain.cn/api/v1',
          MOCK_API: false,
          MOCK_WECHAT_AUTH: false,
          MOCK_REWARDED_AD: false,
          MOCK_AD_OUTCOME: 'completed',
          DOWNLOAD_ACCESS_MODE: 'free',
          REWARDED_AD_UNIT_ID: '',
          BANNER_AD_UNIT_ID: ''
        }
      : getConfig()
    assertProductionSafe(config)
    assertRuntimeSafe(config, 'release')
  } catch (error) {
    fail(`生产发布配置无效：${error.message}`)
  }
}

if (failures.length) {
  console.error(failures.map((item) => `- ${item}`).join('\n'))
  process.exit(1)
}

console.log(`Mini Program validation PASS (${allFiles.length} files checked)`)
