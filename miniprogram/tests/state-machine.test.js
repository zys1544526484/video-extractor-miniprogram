const test = require('node:test')
const assert = require('node:assert/strict')
const { HOME_TRANSITIONS, RESULT_TRANSITIONS, createStateMachine } = require('../utils/state-machine')

test('home state machine completes parse flow', () => {
  const machine = createStateMachine('idle', HOME_TRANSITIONS)
  machine.transition('checking')
  machine.transition('parsing')
  machine.transition('idle')
  assert.equal(machine.state, 'idle')
})

test('home state machine rejects duplicate parse transition', () => {
  const machine = createStateMachine('idle', HOME_TRANSITIONS)
  assert.throws(() => machine.transition('parsing'), /非法状态转换/)
})

test('home state machine supports persistent job completion', () => {
  const machine = createStateMachine('idle', HOME_TRANSITIONS)
  machine.transition('checking')
  machine.transition('parsing')
  machine.transition('ready')
  assert.equal(machine.state, 'ready')
})

test('result state machine covers download and save', () => {
  const machine = createStateMachine('loading', RESULT_TRANSITIONS)
  machine.transition('ready')
  machine.transition('downloading')
  machine.transition('saving')
  machine.transition('success')
  assert.equal(machine.state, 'success')
})
