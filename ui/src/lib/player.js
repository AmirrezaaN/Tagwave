// The built-in player: one shared <audio> element driven by the store.
import { watch } from 'vue'
import { state, visibleFiles, fileMap, updateSettings, toast } from './store.js'
import { call, withToken } from './api.js'
import { errorText } from './i18n.js'

const audio = new Audio()
audio.preload = 'auto'
let loadedKey = ''
let volTimer = null

audio.addEventListener('timeupdate', () => { state.player.time = audio.currentTime })
audio.addEventListener('durationchange', () => { state.player.duration = isFinite(audio.duration) ? audio.duration : 0 })
audio.addEventListener('play', () => { state.player.playing = true })
audio.addEventListener('pause', () => { state.player.playing = false })
audio.addEventListener('waiting', () => { state.player.buffering = true })
audio.addEventListener('playing', () => { state.player.buffering = false })
audio.addEventListener('ended', () => { next(true) })
audio.addEventListener('error', () => {
  if (audio.src) { state.player.error = true; state.player.loading = false; state.player.playing = false }
})

export function initVolume() {
  audio.volume = Math.max(0, Math.min(1, Number(state.settings.volume ?? 0.8)))
  state.player.volume = audio.volume
}

export async function playFile(id, { startAt = 0, autoplay = true } = {}) {
  const file = fileMap.value.get(id)
  if (!file) return
  state.player.id = id
  state.player.loading = true
  state.player.error = false
  state.player.time = startAt
  state.player.duration = file.info.duration || 0
  try {
    const src = await call('player.source', { id })
    if (state.player.id !== id) return
    loadedKey = id + ':' + file.version
    audio.src = withToken(src.url)
    if (startAt) {
      await new Promise((resolve) => {
        audio.addEventListener('loadedmetadata', resolve, { once: true })
        setTimeout(resolve, 3000)
      })
      audio.currentTime = Math.min(startAt, Math.max(0, (audio.duration || startAt) - 0.25))
    }
    if (autoplay) await audio.play()
  } catch (e) {
    if (e?.name !== 'AbortError') {
      state.player.error = true
      if (e?.code) toast(errorText(e), 'error')
    }
  } finally {
    if (state.player.id === id) state.player.loading = false
  }
}

export function toggle() {
  if (!state.player.id) {
    const id = state.selection[0] || visibleFiles.value[0]?.id
    if (id) playFile(id)
    return
  }
  if (audio.paused) audio.play().catch(() => {})
  else audio.pause()
}

export function next(auto = false) {
  const order = visibleFiles.value.map((f) => f.id)
  const i = order.indexOf(state.player.id)
  if (i >= 0 && i < order.length - 1) playFile(order[i + 1])
  else if (auto) { audio.pause(); state.player.playing = false }
}

export function prev() {
  if (audio.currentTime > 3) { audio.currentTime = 0; return }
  const order = visibleFiles.value.map((f) => f.id)
  const i = order.indexOf(state.player.id)
  if (i > 0) playFile(order[i - 1])
  else audio.currentTime = 0
}

export function seek(sec) {
  if (!audio.src) return
  audio.currentTime = Math.max(0, Math.min(sec, audio.duration || sec))
  state.player.time = audio.currentTime
}

export function setVolume(v) {
  audio.volume = Math.max(0, Math.min(1, v))
  state.player.volume = audio.volume
  clearTimeout(volTimer)
  volTimer = setTimeout(() => updateSettings({ volume: audio.volume }).catch(() => {}), 600)
}

export function currentTime() {
  return audio.currentTime
}

export function stop() {
  audio.pause()
  audio.removeAttribute('src')
  audio.load()
  state.player.id = null
  state.player.playing = false
}

// After the playing file is saved (tags changed size), reload it at the same position.
watch(() => state.player.version, () => {
  const id = state.player.id
  const file = id && fileMap.value.get(id)
  if (!file || loadedKey === id + ':' + file.version) return
  playFile(id, { startAt: audio.currentTime, autoplay: !audio.paused })
})

// If the playing file disappears from the list, stop.
watch(() => state.player.id, (id) => { if (!id && audio.src) stop() })
