<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ShieldCheck, ScanLine, RotateCcw, LoaderCircle, Info } from '@lucide/vue'
import Modal from './Modal.vue'
import { closeDialog, toast } from '../lib/store.js'
import { call, blobUrl } from '../lib/api.js'
import { t, errorText } from '../lib/i18n.js'
import { dims, size } from '../lib/format.js'

const props = defineProps({ pic: Object, onDone: Function })
const MIN = 16
const caps = ref(null)
const W = ref(0)
const H = ref(0)
const mode = ref('lossless')
const aspect = ref('square')
const rect = ref({ x: 0, y: 0, w: 0, h: 0 })
const box = ref(null)
const scale = ref(1)
const busy = ref(false)
const loaded = ref(false)

const lossless = computed(() => mode.value === 'lossless' && caps.value?.lossless)
const snapOn = computed(() => lossless.value && caps.value?.isJpeg)
const mw = computed(() => (snapOn.value ? caps.value.mcu[0] : 1))
const mh = computed(() => (snapOn.value ? caps.value.mcu[1] : 1))
const ratio = computed(() => (aspect.value === 'square' ? 1 : aspect.value === 'original' ? W.value / H.value : 0))
const outFormat = computed(() => (lossless.value && caps.value?.isJpeg ? 'JPEG' : 'PNG'))

onMounted(async () => {
  try {
    caps.value = await call('images.cropInfo', { blob: props.pic.blob })
    if (!caps.value.lossless) mode.value = 'free'
  } catch (e) { toast(errorText(e), 'error'); closeDialog() }
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

function onImgLoad(e) {
  W.value = e.target.naturalWidth
  H.value = e.target.naturalHeight
  layout()
  reset()
  loaded.value = true
}
function layout() {
  const el = box.value
  if (!el || !W.value) return
  scale.value = Math.min(el.clientWidth / W.value, el.clientHeight / H.value, 4)
}
const snapDown = (v, m) => Math.floor(v / m) * m
const snapNear = (v, m) => Math.round(v / m) * m

function fix(r, handle) {
  const Wv = W.value
  const Hv = H.value
  let { x, y, w, h } = r
  const R = x + w
  const B = y + h
  const left = handle === 'move' || handle.includes('w')
  const top = handle === 'move' || handle.includes('n')
  if (handle === 'move') {
    x = Math.max(0, Math.min(x, Wv - w))
    y = Math.max(0, Math.min(y, Hv - h))
    x = Math.min(snapNear(x, mw.value), snapDown(Wv - w, mw.value))
    y = Math.min(snapNear(y, mh.value), snapDown(Hv - h, mh.value))
    x = Math.max(0, x); y = Math.max(0, y)
  } else {
    if (left) { x = Math.max(0, Math.min(snapNear(x, mw.value), R - MIN)); x = snapDown(x, mw.value); w = R - x }
    if (top) { y = Math.max(0, Math.min(snapNear(y, mh.value), B - MIN)); y = snapDown(y, mh.value); h = B - y }
    w = Math.max(MIN, Math.min(w, Wv - x))
    h = Math.max(MIN, Math.min(h, Hv - y))
    if (ratio.value) {
      const rr = ratio.value
      if (w / h > rr) w = h * rr
      else h = w / rr
      w = Math.min(w, Wv - x); h = Math.min(h, Hv - y)
      if (w / h > rr) w = h * rr
      else h = w / rr
    }
  }
  return { x: Math.round(x), y: Math.round(y), w: Math.max(1, Math.floor(w)), h: Math.max(1, Math.floor(h)) }
}

function reset() {
  let w = W.value
  let h = H.value
  if (ratio.value) {
    if (w / h > ratio.value) w = h * ratio.value
    else h = w / ratio.value
  }
  const x = snapDown((W.value - w) / 2, mw.value)
  const y = snapDown((H.value - h) / 2, mh.value)
  rect.value = fix({ x, y, w, h }, 'se')
}

function setAspect(a) { aspect.value = a; rect.value = fix({ ...rect.value }, 'se') }
function setMode(m) { mode.value = m; rect.value = fix({ ...rect.value }, 'move') }

let drag = null
function startDrag(e, handle) {
  e.preventDefault()
  e.stopPropagation()
  drag = { handle, sx: e.clientX, sy: e.clientY, start: { ...rect.value } }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', endDrag)
}
function onMove(e) {
  if (!drag) return
  const dx = (e.clientX - drag.sx) / scale.value
  const dy = (e.clientY - drag.sy) / scale.value
  const s = drag.start
  const h = drag.handle
  let r = { ...s }
  if (h === 'move') { r.x = s.x + dx; r.y = s.y + dy }
  else {
    if (h.includes('w')) { r.x = s.x + dx; r.w = s.w - dx }
    if (h.includes('e')) r.w = s.w + dx
    if (h.includes('n')) { r.y = s.y + dy; r.h = s.h - dy }
    if (h.includes('s')) r.h = s.h + dy
  }
  rect.value = fix(r, h)
}
function endDrag() {
  drag = null
  window.removeEventListener('pointermove', onMove)
  window.removeEventListener('pointerup', endDrag)
}
function onKey(e) {
  if (e.target.tagName === 'INPUT') return
  const step = e.shiftKey ? 10 : 1
  const d = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key]
  if (d) {
    e.preventDefault()
    const r = { ...rect.value }
    r.x += d[0] * Math.max(mw.value, step)
    r.y += d[1] * Math.max(mh.value, step)
    rect.value = fix(r, 'move')
  } else if (e.key === 'Enter') { e.preventDefault(); apply() }
}

async function autoBorders() {
  try {
    const r = await call('images.detectBorders', { blob: props.pic.blob })
    aspect.value = 'free'
    const x = snapDown(r.x, mw.value)
    const y = snapDown(r.y, mh.value)
    rect.value = fix({ x, y, w: r.w + (r.x - x), h: r.h + (r.y - y) }, 'se')
  } catch (e) { toast(errorText(e), 'error') }
}

async function apply() {
  if (busy.value) return
  busy.value = true
  try {
    const r = rect.value
    const img = await call('images.crop', { blob: props.pic.blob, x: r.x, y: r.y, w: r.w, h: r.h, mode: lossless.value ? 'lossless' : 'free' })
    props.onDone?.(img)
    closeDialog()
  } catch (e) {
    toast(errorText(e), 'error')
  } finally {
    busy.value = false
  }
}

const style = computed(() => ({
  left: rect.value.x * scale.value + 'px', top: rect.value.y * scale.value + 'px',
  width: rect.value.w * scale.value + 'px', height: rect.value.h * scale.value + 'px',
}))
const handles = computed(() => (ratio.value ? ['nw', 'ne', 'sw', 'se'] : ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w']))
</script>

<template>
  <Modal :title="t('cr.title')" width="980px" @close="closeDialog">
    <div class="crop">
      <div class="stage" ref="box">
        <div class="canvas" :style="{ width: W * scale + 'px', height: H * scale + 'px' }">
          <img :src="blobUrl(pic.blob)" alt="" draggable="false" @load="onImgLoad" />
          <div v-if="loaded" class="sel" :style="style" @pointerdown="startDrag($event, 'move')">
            <i class="third v1" /><i class="third v2" /><i class="third h1" /><i class="third h2" />
            <span v-for="h in handles" :key="h" class="handle" :class="h" @pointerdown="startDrag($event, h)" />
          </div>
        </div>
      </div>

      <aside class="side">
        <div class="group">
          <label class="label">{{ t('cr.aspect') }}</label>
          <div class="seg">
            <button :class="{ on: aspect === 'square' }" @click="setAspect('square')">{{ t('cr.aSquare') }}</button>
            <button :class="{ on: aspect === 'original' }" @click="setAspect('original')">{{ t('cr.aOriginal') }}</button>
            <button :class="{ on: aspect === 'free' }" @click="setAspect('free')">{{ t('cr.aFree') }}</button>
          </div>
        </div>

        <div class="group" v-if="caps">
          <label class="mode" :class="{ on: lossless }">
            <input type="radio" name="mode" :checked="mode === 'lossless'" :disabled="!caps.lossless" @change="setMode('lossless')" />
            <div>
              <b><ShieldCheck /> {{ t('cr.lossless') }}</b>
              <span v-if="!caps.lossless">{{ t('cr.unavailable') }}</span>
              <span v-else-if="caps.isJpeg">{{ t('cr.losslessOn', { w: caps.mcu[0], h: caps.mcu[1] }) }}</span>
              <span v-else>{{ t('cr.pngNote') }}</span>
            </div>
          </label>
          <label class="mode" :class="{ on: !lossless }" v-if="caps.isJpeg">
            <input type="radio" name="mode" :checked="mode === 'free'" @change="setMode('free')" />
            <div><b>{{ t('cr.aFree') }}</b><span>{{ t('cr.free') }}</span></div>
          </label>
        </div>

        <div class="row">
          <button class="btn sm" @click="autoBorders"><ScanLine /> {{ t('cr.borders') }}</button>
          <button class="btn sm ghost" @click="reset"><RotateCcw /> {{ t('cr.reset') }}</button>
        </div>

        <div class="result card">
          <div class="label">{{ t('cr.output') }}</div>
          <div class="big ltr">{{ dims(rect.w, rect.h) }}</div>
          <div class="muted ltr">{{ outFormat }} · {{ t('cr.aOriginal') }} {{ dims(W, H) }} · {{ size(pic.size) }}</div>
        </div>
        <p class="tip"><Info /> ← ↑ → ↓ · Shift · Enter</p>
      </aside>
    </div>
    <template #footer>
      <button class="btn" @click="closeDialog">{{ t('a.cancel') }}</button>
      <button class="btn primary" :disabled="busy || !loaded" @click="apply"><LoaderCircle v-if="busy" class="spin" /> {{ t('cr.apply') }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.crop { display: grid; grid-template-columns: 1fr 280px; gap: 18px; }
.stage { height: 520px; display: grid; place-items: center; border-radius: 12px; overflow: hidden; background: #0a0b0f; }
.canvas { position: relative; user-select: none; touch-action: none; }
.canvas img { width: 100%; height: 100%; display: block; }
.sel { position: absolute; cursor: move; outline: 1.5px solid #fff; box-shadow: 0 0 0 9999px rgba(5, 6, 10, .6); }
.third { position: absolute; background: rgba(255, 255, 255, .28); pointer-events: none; }
.third.v1, .third.v2 { top: 0; bottom: 0; width: 1px; }
.third.h1, .third.h2 { left: 0; right: 0; height: 1px; }
.third.v1 { left: 33.33%; } .third.v2 { left: 66.66%; } .third.h1 { top: 33.33%; } .third.h2 { top: 66.66%; }
.handle { position: absolute; width: 14px; height: 14px; background: #fff; border-radius: 3px; box-shadow: 0 1px 4px rgba(0,0,0,.5); }
.handle.nw { left: -7px; top: -7px; cursor: nwse-resize; } .handle.se { right: -7px; bottom: -7px; cursor: nwse-resize; }
.handle.ne { right: -7px; top: -7px; cursor: nesw-resize; } .handle.sw { left: -7px; bottom: -7px; cursor: nesw-resize; }
.handle.n { left: calc(50% - 7px); top: -7px; cursor: ns-resize; } .handle.s { left: calc(50% - 7px); bottom: -7px; cursor: ns-resize; }
.handle.e { right: -7px; top: calc(50% - 7px); cursor: ew-resize; } .handle.w { left: -7px; top: calc(50% - 7px); cursor: ew-resize; }
.side { display: flex; flex-direction: column; gap: 16px; }
.seg { display: flex; background: var(--surface-2); border: 1px solid var(--border); border-radius: 9px; padding: 3px; gap: 3px; }
.seg button { flex: 1; height: 28px; border: 0; background: transparent; border-radius: 6px; color: var(--muted); font-weight: 600; font-size: 12.5px; }
.seg button.on { background: var(--surface-3); color: var(--text); box-shadow: 0 1px 3px rgba(0,0,0,.2); }
.group { display: flex; flex-direction: column; gap: 8px; }
.mode { display: flex; gap: 10px; padding: 10px 12px; border-radius: 10px; border: 1px solid var(--border); cursor: pointer; transition: .15s; }
.mode.on { border-color: var(--primary); background: var(--primary-soft); }
.mode input { accent-color: var(--primary); margin-top: 3px; }
.mode b { display: flex; align-items: center; gap: 6px; font-size: 13px; }
.mode b svg { width: 14px; height: 14px; color: var(--success); }
.mode span { display: block; font-size: 11.5px; color: var(--muted); margin-top: 3px; line-height: 1.5; }
.result { padding: 12px 14px; }
.big { font-size: 22px; font-weight: 700; letter-spacing: -.01em; }
.result .muted { font-size: 12px; }
.tip { display: flex; align-items: center; gap: 6px; font-size: 11.5px; color: var(--faint); margin: auto 0 0; }
.tip svg { width: 13px; height: 13px; }
</style>
