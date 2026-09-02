function normalizeShareText(value) {
  return String(value || '').replace(/\u0000/g, '').trim().slice(0, 5000)
}

function hasHttpUrl(value) {
  return /https?:\/\/[^\s]+/i.test(normalizeShareText(value))
}

module.exports = { normalizeShareText, hasHttpUrl }

