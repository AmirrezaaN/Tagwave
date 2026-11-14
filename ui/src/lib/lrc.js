// LRC helpers for the lyrics sync editor.

const TIME = /^\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]/
const META = /^\[(ar|ti|al|au|by|length|offset|re|ve|#):(.*)\]\s*$/i

export function parse(text) {
  const lines = []
  const meta = []
  for (const raw of (text || '').split(/\r?\n/)) {
    const line = raw.trim()
    if (META.test(line) && !TIME.test(line)) { meta.push(line); continue }
    let rest = line
    let time = null
    const m = TIME.exec(rest)
    if (m) {
      const frac = m[3] ? parseInt(m[3].padEnd(3, '0').slice(0, 3), 10) : 0
      time = (parseInt(m[1], 10) * 60 + parseInt(m[2], 10)) * 1000 + frac
      rest = rest.slice(m[0].length)
      // drop additional stamps on the same line (keep first)
      while (TIME.test(rest)) rest = rest.replace(TIME, '')
    }
    lines.push({ time, text: rest.trim() })
  }
  while (lines.length && !lines[lines.length - 1].text && lines[lines.length - 1].time === null) lines.pop()
  return { lines, meta }
}

export function stamp(ms) {
  ms = Math.max(0, Math.round(ms))
  const m = Math.floor(ms / 60000)
  const s = Math.floor((ms % 60000) / 1000)
  const cs = Math.floor((ms % 1000) / 10)
  return `[${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${String(cs).padStart(2, '0')}]`
}

export function serialize({ lines, meta }) {
  const out = [...(meta || [])]
  for (const l of lines) out.push((l.time !== null && l.time !== undefined ? stamp(l.time) : '') + l.text)
  return out.join('\n')
}

export function isSynced(text) {
  return parse(text).lines.some((l) => l.time !== null)
}
