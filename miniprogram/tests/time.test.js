const test = require('node:test')
const assert = require('node:assert/strict')
const { entitlementView } = require('../utils/time')

test('expired entitlement is rejected', () => {
  const view = entitlementView({ entitled: true, unlock_until: '2026-01-01T00:00:00Z' }, Date.parse('2026-01-01T00:00:01Z'))
  assert.equal(view.entitled, false)
})

test('valid entitlement reports server-relative remaining time', () => {
  const now = Date.parse('2026-09-01T00:00:00Z')
  const view = entitlementView({ entitled: true, unlock_until: '2026-09-01T12:34:00Z' }, now)
  assert.equal(view.entitled, true)
  assert.match(view.label, /12小时34分/)
})

