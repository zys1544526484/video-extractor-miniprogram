const HOME_TRANSITIONS = {
  idle: ['checking'],
  checking: ['parsing', 'error', 'idle'],
  parsing: ['idle', 'error'],
  error: ['checking', 'idle']
}

const RESULT_TRANSITIONS = {
  loading: ['ready', 'error'],
  ready: ['loading', 'downloading', 'error'],
  downloading: ['saving', 'success', 'error'],
  saving: ['success', 'error'],
  success: ['downloading', 'ready'],
  error: ['loading', 'downloading', 'ready']
}

function createStateMachine(initial, transitions) {
  let state = initial
  return {
    get state() {
      return state
    },
    can(next) {
      return Boolean(transitions[state] && transitions[state].includes(next))
    },
    transition(next) {
      if (next === state) return state
      if (!this.can(next)) throw new Error(`非法状态转换：${state} -> ${next}`)
      state = next
      return state
    }
  }
}

module.exports = { HOME_TRANSITIONS, RESULT_TRANSITIONS, createStateMachine }

