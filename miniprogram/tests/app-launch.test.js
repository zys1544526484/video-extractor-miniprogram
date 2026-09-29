const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const config = require('../config')
const development = require('../config/env')

function launch(settings, envVersion) {
  let app
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app.js'), 'utf8'), {
    require: () => ({ ...config, getConfig: () => settings }),
    App: (value) => { app = value },
    wx: { getAccountInfoSync: () => ({ miniProgram: { envVersion } }) }
  })
  app.onLaunch()
  return app
}

test('the real app launches with the checked-in development configuration', () => {
  assert.equal(launch(development, 'develop').globalData.config, development)
})

test('the real app rejects development builds in trial and release', () => {
  for (const envVersion of ['trial', 'release']) {
    assert.throws(() => launch(development, envVersion), /禁止打包开发 Mock/)
  }
})

test('production safety also applies inside the developer simulator', () => {
  assert.throws(() => launch({ ...development, APP_ENV: 'production' }, 'develop'), /禁止启用 Mock/)
})
