export function duration(sec) {
  if (!sec || !isFinite(sec)) return '0:00'
  sec = Math.round(sec)
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  const pad = (x) => String(x).padStart(2, '0')
  return h ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`
}

export function size(bytes) {
  if (!bytes && bytes !== 0) return ''
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let v = bytes
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(v >= 100 || i === 0 ? 0 : 1)} ${units[i]}`
}

export function kbps(bps) {
  return bps ? `${Math.round(bps / 1000)} kbps` : ''
}

export function khz(hz) {
  if (!hz) return ''
  const k = hz / 1000
  return `${Number.isInteger(k) ? k : k.toFixed(1)} kHz`
}

export function dims(w, h) {
  return w && h ? `${w}×${h}` : ''
}

// "24-bit / 96 kHz" style quality summary
export function qualityLine(info) {
  const parts = []
  if (info.bitsPerSample && info.lossless) parts.push(`${info.bitsPerSample}-bit`)
  if (info.sampleRate) parts.push(khz(info.sampleRate))
  if (!info.lossless && info.bitrate) parts.push(kbps(info.bitrate) + (info.bitrateMode ? ' ' + info.bitrateMode : ''))
  return parts.join(' · ')
}
