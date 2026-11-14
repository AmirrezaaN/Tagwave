<script setup>
import { computed, ref, watch, onBeforeUnmount, nextTick } from 'vue'
import { Timer, Upload, Download, Eraser, Play, Pause, Undo2, Check, Plus, Minus, MicVocal } from '@lucide/vue'
import { state, toast } from '../lib/store.js'
import { call } from '../lib/api.js'
import { t, errorText } from '../lib/i18n.js'
import { parse, serialize, isSynced, stamp } from '../lib/lrc.js'
import { playFile, toggle, currentTime, seek } from '../lib/player.js'

const props = defineProps({ ids: Array })
const id = computed(() => (props.ids.length === 1 ? props.ids[0] : null))
const text = computed({
  get: () => (id.value ? state.drafts[id.value]?.fields.lyrics || '' : ''),
  set: (v) => { if (id.value) state.drafts[id.value].fields.lyrics = v },
})
const synced = computed(() => isSynced(text.value))
const syncing = ref(false)
const doc = ref({ lines: [], meta: [] })
const cursor = ref(0)
const listEl = ref(null)
const thisPlaying = computed(() => state.player.id === id.value)

function start() {
  doc.value = parse(text.value)
  doc.value.lines = doc.value.lines.filter((l, i, arr) => l.text || l.time !== null || i < arr.length - 1)
  cursor.value = Math.max(0, doc.value.lines.findIndex((l) => l.time === null))
  if (cursor.value < 0) cursor.value = 0
  syncing.value = true
  state.lyricsSync = true
  if (!thisPlaying.value) playFile(id.value)
  window.addEventListener('keydown', onKey, true)
}
function stop() {
  syncing.value = false
  state.lyricsSync = false
  window.removeEventListener('keydown', onKey, true)
}
onBeforeUnmount(stop)
watch(id, () => stop())

function commit() { text.value = serialize(doc.value) }
function doStamp() {
  if (!doc.value.lines.length) return
  const i = Math.min(cursor.value, doc.value.lines.length - 1)
  doc.value.lines[i].time = Math.round(currentTime() * 1000)
  cursor.value = Math.min(i + 1, doc.value.lines.length)
  commit()
  scrollToCursor()
}
function back() { cursor.value = Math.max(0, cursor.value - 1); scrollToCursor() }
function shiftAll(ms) {
  for (const l of doc.value.lines) if (l.time !== null) l.time = Math.max(0, l.time + ms)
  commit()
}
function onKey(e) {
  if (!syncing.value) return
  if (e.code === 'Space' || e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); doStamp() }
  else if (e.key === 'Backspace' || e.key === 'ArrowUp') { e.preventDefault(); back() }
  else if (e.key === 'ArrowDown') { e.preventDefault(); cursor.value = Math.min(doc.value.lines.length, cursor.value + 1); scrollToCursor() }
  else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); stop() }
}
function scrollToCursor() {
  nextTick(() => listEl.value?.querySelector('.cur')?.scrollIntoView({ block: 'center', behavior: 'smooth' }))
}
const active = computed(() => {
  if (!thisPlaying.value) return -1
  const ms = state.player.time * 1000
  let best = -1
  doc.value.lines.forEach((l, i) => { if (l.time !== null && l.time <= ms) best = i })
  return best
})

function removeTimes() {
  const d = parse(text.value)
  text.value = d.lines.map((l) => l.text).join('\n')
}
async function importLrc() {
  try {
    const res = await call('lyrics.import')
    if (res.text !== null && res.text !== undefined) text.value = res.text
  } catch (e) { toast(errorText(e), 'error') }
}
async function exportLrc() {
  const f = state.files.find((x) => x.id === id.value)
  try {
    await call('lyrics.export', { text: text.value, name: f ? f.name.replace(/\.[^.]+$/, '') : 'lyrics' })
  } catch (e) { toast(errorText(e), 'error') }
}
</script>

<template>
  <div class="lyrics" v-if="id">
    <div class="bar">
      <span class="badge" :class="synced ? 'primary' : ''"><Timer v-if="synced" />{{ synced ? t('ly.synced') : t('ly.plain') }}</span>
      <div class="grow" />
      <template v-if="!syncing">
        <button class="btn sm" @click="start" :disabled="!text.trim()"><MicVocal /> {{ t('ly.sync') }}</button>
        <button class="btn sm ghost" @click="importLrc"><Upload /> {{ t('ly.import') }}</button>
        <button class="btn sm ghost" @click="exportLrc" :disabled="!text.trim()"><Download /> {{ t('ly.export') }}</button>
        <button class="btn sm ghost" @click="removeTimes" :disabled="!synced"><Eraser /> {{ t('ly.removeTimes') }}</button>
      </template>
      <template v-else>
        <span class="muted small">{{ t('ly.shift') }}</span>
        <button class="btn sm ghost icon" @click="shiftAll(-100)" title="-0.1s"><Minus /></button>
        <button class="btn sm ghost icon" @click="shiftAll(100)" title="+0.1s"><Plus /></button>
        <button class="btn sm primary" @click="stop"><Check /> {{ t('ly.syncStop') }}</button>
      </template>
    </div>

    <textarea v-if="!syncing" v-model="text" class="textarea editor" dir="auto" spellcheck="false" :placeholder="t('ly.placeholder')" />

    <div v-else class="sync">
      <p class="hint">{{ t('ly.tapHint') }}</p>
      <div class="sync-controls">
        <button class="btn" @click="toggle"><Pause v-if="state.player.playing && thisPlaying" /><Play v-else /></button>
        <button class="btn gradient lg stamp" @click="doStamp"><Timer /> {{ t('ly.stamp') }} <span class="kbd">Space</span></button>
        <button class="btn" @click="back"><Undo2 /> {{ t('ly.back') }}</button>
        <span class="muted small ltr">{{ t('ly.line', { n: Math.min(cursor + 1, doc.lines.length), m: doc.lines.length }) }}</span>
      </div>
      <div ref="listEl" class="lines">
        <div v-for="(l, i) in doc.lines" :key="i" class="line" :class="{ cur: i === cursor, active: i === active, done: l.time !== null }"
             @click="cursor = i" @dblclick="l.time !== null && seek(l.time / 1000)">
          <span class="time ltr">{{ l.time !== null ? stamp(l.time).slice(1, -1) : '— : —' }}</span>
          <span class="txt" dir="auto">{{ l.text || '♪' }}</span>
        </div>
      </div>
    </div>
  </div>
  <p v-else class="muted">{{ t('ly.single') }}</p>
</template>

<style scoped>
.lyrics { display: flex; flex-direction: column; gap: 12px; height: 100%; max-width: 900px; }
.bar { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.small { font-size: 12px; }
.editor { flex: 1; min-height: 360px; font-size: 14.5px; line-height: 1.9; resize: none; }
.sync { display: flex; flex-direction: column; gap: 12px; min-height: 0; flex: 1; }
.hint { margin: 0; color: var(--muted); font-size: 12.5px; }
.sync-controls { display: flex; align-items: center; gap: 8px; }
.stamp { min-width: 200px; }
.stamp .kbd { color: rgba(255,255,255,.8); border-color: rgba(255,255,255,.4); }
.lines { flex: 1; min-height: 300px; max-height: 52vh; overflow: auto; border: 1px solid var(--border); border-radius: var(--radius); padding: 8px; background: var(--surface); }
.line { display: flex; gap: 14px; align-items: baseline; padding: 7px 10px; border-radius: 8px; cursor: pointer; transition: background .12s; }
.line:hover { background: var(--hover); }
.line .time { font-family: var(--mono); font-size: 12px; color: var(--faint); min-width: 64px; }
.line.done .time { color: var(--success); }
.line .txt { font-size: 14.5px; color: var(--text-2); }
.line.cur { background: var(--primary-soft); box-shadow: inset 3px 0 0 var(--primary); }
[dir='rtl'] .line.cur { box-shadow: inset -3px 0 0 var(--primary); }
.line.active .txt { color: var(--text); font-weight: 650; }
</style>
