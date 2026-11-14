<script setup>
import { computed, ref, onMounted, watch } from 'vue'
import { Play, Pause, SkipBack, SkipForward, Volume2, Volume1, VolumeX, Music, LoaderCircle, TriangleAlert } from '@lucide/vue'
import { state, fileMap } from '../lib/store.js'
import { thumbUrl } from '../lib/api.js'
import { t } from '../lib/i18n.js'
import { duration } from '../lib/format.js'
import { toggle, next, prev, seek, setVolume, initVolume } from '../lib/player.js'

const file = computed(() => (state.player.id ? fileMap.value.get(state.player.id) : null))
const fields = computed(() => (file.value ? (state.drafts[file.value.id]?.fields || file.value.fields) : null))
const cover = computed(() => file.value && (state.drafts[file.value.id]?.pictures || file.value.pictures)[0]?.blob)
const pct = computed(() => (state.player.duration ? (state.player.time / state.player.duration) * 100 : 0))
const bar = ref(null)
const dragging = ref(false)
const hoverPct = ref(null)
let lastVol = 0.8

onMounted(() => initVolume())
watch(() => state.ready, (r) => r && initVolume())

function posToTime(e) {
  const r = bar.value.getBoundingClientRect()
  const x = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width))
  return x
}
function down(e) {
  if (!file.value) return
  dragging.value = true
  seek(posToTime(e) * state.player.duration)
  const move = (ev) => seek(posToTime(ev) * state.player.duration)
  const up = () => { dragging.value = false; window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up) }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', up)
}
function hover(e) { hoverPct.value = posToTime(e) }
function muteToggle() {
  if (state.player.volume > 0) { lastVol = state.player.volume; setVolume(0) } else setVolume(lastVol || 0.8)
}
function onVolWheel(e) { setVolume((state.player.volume ?? 0.8) + (e.deltaY < 0 ? 0.05 : -0.05)) }

function onKey(e) {
  const el = e.target
  if (e.code === 'Space' && !(el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.tagName === 'BUTTON')) {
    if (state.dialog?.name === 'crop' || state.lyricsSync) return
    e.preventDefault()
    toggle()
  }
}
onMounted(() => window.addEventListener('keydown', onKey))
</script>

<template>
  <footer class="player">
    <div class="now">
      <div class="art">
        <img v-if="cover" :src="thumbUrl(cover, 128)" alt="" />
        <Music v-else />
      </div>
      <div class="nt" v-if="file">
        <div class="ellipsis title bidi">{{ fields.title || file.name }}</div>
        <div class="ellipsis sub bidi">{{ fields.artist || t('list.unknownArtist') }}</div>
      </div>
      <div class="nt muted" v-else>{{ t('pl.nothing') }}</div>
    </div>

    <div class="center" dir="ltr">
      <div class="controls">
        <button class="ctl" @click="prev" :disabled="!file" :aria-label="t('a.previous')"><SkipBack /></button>
        <button class="ctl play" @click="toggle" :disabled="!state.files.length" :aria-label="state.player.playing ? t('a.pause') : t('a.play')">
          <LoaderCircle v-if="state.player.loading" class="spin" />
          <Pause v-else-if="state.player.playing" />
          <Play v-else />
        </button>
        <button class="ctl" @click="next()" :disabled="!file" :aria-label="t('a.next')"><SkipForward /></button>
      </div>
      <div class="timeline">
        <span class="time">{{ duration(state.player.time) }}</span>
        <div ref="bar" class="bar" :class="{ active: dragging, disabled: !file }" @pointerdown="down" @pointermove="hover" @pointerleave="hoverPct = null">
          <div class="track"><div class="fill" :style="{ width: pct + '%' }" /></div>
          <div class="knob" :style="{ left: pct + '%' }" />
          <div v-if="hoverPct !== null && file" class="tip" :style="{ left: hoverPct * 100 + '%' }">{{ duration(hoverPct * state.player.duration) }}</div>
        </div>
        <span class="time">{{ duration(state.player.duration) }}</span>
      </div>
      <div v-if="state.player.loading && file && !file.playable" class="preparing">{{ t('pl.preparing') }}</div>
      <div v-if="state.player.error" class="preparing err"><TriangleAlert /> {{ t('e.error') }}</div>
    </div>

    <div class="vol" dir="ltr" @wheel.prevent="onVolWheel">
      <button class="ctl sm" @click="muteToggle" :aria-label="t('pl.volume')">
        <VolumeX v-if="!state.player.volume" /><Volume1 v-else-if="state.player.volume < 0.5" /><Volume2 v-else />
      </button>
      <input type="range" min="0" max="1" step="0.01" :value="state.player.volume ?? 0.8"
             @input="setVolume(+$event.target.value)" :style="{ '--v': ((state.player.volume ?? 0.8) * 100) + '%' }" :aria-label="t('pl.volume')" />
    </div>
  </footer>
</template>

<style scoped>
.player {
  display: grid; grid-template-columns: minmax(220px, 1fr) minmax(360px, 2fr) minmax(160px, 1fr); align-items: center;
  gap: 18px; padding: 0 18px; background: var(--glass); backdrop-filter: blur(18px) saturate(1.4);
  border-top: 1px solid var(--border); position: relative; z-index: 4;
}
.now { display: flex; align-items: center; gap: 12px; min-width: 0; }
.art { width: 46px; height: 46px; border-radius: 8px; overflow: hidden; background: var(--surface-3); display: grid; place-items: center; color: var(--faint); flex: none; box-shadow: 0 4px 12px rgba(0,0,0,.3); }
.art img { width: 100%; height: 100%; object-fit: cover; }
.art svg { width: 20px; height: 20px; }
.nt { min-width: 0; }
.title { font-weight: 600; }
.sub { font-size: 12px; color: var(--muted); }
.center { display: flex; flex-direction: column; align-items: center; gap: 4px; position: relative; }
.controls { display: flex; align-items: center; gap: 10px; }
.ctl { border: 0; background: transparent; color: var(--text-2); width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center; transition: .15s; }
.ctl:hover:not(:disabled) { color: var(--text); background: var(--hover); }
.ctl:disabled { opacity: .35; cursor: default; }
.ctl svg { width: 17px; height: 17px; }
.ctl.play { width: 36px; height: 36px; background: var(--text); color: var(--bg); }
.ctl.play:hover:not(:disabled) { background: var(--text); transform: scale(1.06); color: var(--bg); }
.ctl.play svg { width: 17px; height: 17px; fill: currentColor; }
.ctl.sm { width: 28px; height: 28px; }
.timeline { display: flex; align-items: center; gap: 10px; width: 100%; max-width: 620px; }
.time { font-size: 11px; color: var(--muted); font-variant-numeric: tabular-nums; min-width: 36px; text-align: center; }
.bar { position: relative; flex: 1; height: 16px; display: flex; align-items: center; cursor: pointer; touch-action: none; }
.bar.disabled { pointer-events: none; opacity: .5; }
.track { width: 100%; height: 4px; border-radius: 4px; background: var(--surface-3); overflow: hidden; }
.fill { height: 100%; background: var(--grad); }
.knob { position: absolute; width: 12px; height: 12px; border-radius: 50%; background: #fff; transform: translateX(-50%) scale(0); transition: transform .12s; box-shadow: 0 1px 4px rgba(0,0,0,.4); }
.bar:hover .knob, .bar.active .knob { transform: translateX(-50%) scale(1); }
.tip { position: absolute; bottom: 18px; transform: translateX(-50%); font-size: 11px; padding: 2px 6px; border-radius: 5px; background: var(--surface-3); color: var(--text); pointer-events: none; white-space: nowrap; }
.preparing { position: absolute; bottom: -14px; font-size: 10.5px; color: var(--muted); display: flex; align-items: center; gap: 4px; }
.preparing.err { color: var(--danger); }
.preparing svg { width: 12px; height: 12px; }
.vol { display: flex; align-items: center; justify-content: flex-end; gap: 6px; justify-self: end; }
.vol input { width: 110px; appearance: none; height: 4px; border-radius: 4px; outline: none; cursor: pointer;
  background: linear-gradient(to right, var(--text-2) var(--v), var(--surface-3) var(--v)); }
.vol input::-webkit-slider-thumb { appearance: none; width: 12px; height: 12px; border-radius: 50%; background: #fff; box-shadow: 0 1px 4px rgba(0,0,0,.4); }
</style>
