<script setup>
import { computed, ref, watch, reactive } from 'vue'
import { Activity, LoaderCircle, BadgeCheck, TriangleAlert, CircleAlert, Info } from '@lucide/vue'
import { toast } from '../lib/store.js'
import { call, waitJob, blobUrl } from '../lib/api.js'
import { t, errorText } from '../lib/i18n.js'
import { khz, duration } from '../lib/format.js'

const props = defineProps({ file: Object })
const cache = (window.__twQuality ||= reactive({}))
const busy = ref(false)
const key = computed(() => (props.file ? props.file.id + ':' + props.file.version : ''))
const res = computed(() => cache[key.value] || null)
watch(key, () => { busy.value = false })

async function analyze() {
  if (!props.file) return
  busy.value = true
  const k = key.value
  try {
    const { jobId } = await call('quality.analyze', { id: props.file.id })
    const job = await waitJob(jobId)
    cache[k] = job.result
  } catch (e) {
    toast(errorText(e), 'error')
  } finally {
    if (key.value === k) busy.value = false
  }
}

const icon = computed(() => {
  const v = res.value?.verdict
  if (v === 'good') return BadgeCheck
  if (v === 'lossy') return Info
  if (v === 'padded-bits') return CircleAlert
  return TriangleAlert
})
const tone = computed(() => ({ good: 'good', lossy: 'neutral', 'padded-bits': 'warn' }[res.value?.verdict] || 'bad'))
const desc = computed(() => {
  const r = res.value
  if (!r) return ''
  const p = { cut: khz(r.cutoffHz), kbps: r.estimatedKbps, rate: khz(r.sampleRate), declared: r.declaredBits, effective: r.effectiveBits }
  if (r.verdict === 'lossy') return r.cutoffHz ? t('q.d.lossyCut', p) : t('q.d.lossy')
  return t('q.d.' + r.verdict, p)
})
const ticks = computed(() => {
  const r = res.value
  if (!r) return []
  const ny = r.nyquistHz
  const step = ny > 40000 ? 10000 : ny > 15000 ? 5000 : 2000
  const out = []
  for (let f = 0; f <= ny; f += step) out.push({ f, pct: (f / ny) * 100 })
  return out
})
const timeTicks = computed(() => {
  const d = res.value?.duration || 0
  if (!d) return []
  const shown = Math.min(d, 600)
  const step = shown > 300 ? 60 : shown > 120 ? 30 : shown > 40 ? 10 : 5
  const out = []
  for (let s = 0; s <= shown; s += step) out.push({ s, pct: (s / shown) * 100 })
  return out
})
</script>

<template>
  <div class="quality" v-if="file">
    <div class="intro">
      <p>{{ t('q.intro') }}</p>
      <button class="btn primary" :disabled="busy" @click="analyze">
        <LoaderCircle v-if="busy" class="spin" /><Activity v-else />
        {{ busy ? t('q.analyzing') : res ? t('q.again') : t('q.analyze') }}
      </button>
    </div>

    <template v-if="res">
      <div class="verdict" :class="tone">
        <component :is="icon" />
        <div>
          <h3>{{ t('q.v.' + res.verdict) }}</h3>
          <p>{{ desc }}</p>
        </div>
      </div>

      <div class="stats">
        <div class="stat" v-if="res.cutoffHz"><span>{{ t('q.cutoff') }}</span><b class="ltr">{{ khz(res.cutoffHz) }}</b></div>
        <div class="stat"><span>{{ t('q.nyquist') }}</span><b class="ltr">{{ khz(res.nyquistHz) }}</b></div>
        <div class="stat" v-if="res.declaredBits"><span>{{ t('q.effBits') }}</span><b class="ltr">{{ res.effectiveBits }} / {{ res.declaredBits }}</b></div>
        <div class="stat" v-if="res.notes.includes('mono-content')"><span>{{ t('d.channels') }}</span><b>{{ t('d.mono') }}</b></div>
      </div>

      <figure class="spectro" dir="ltr">
        <div class="yaxis">
          <span v-for="tk in ticks" :key="tk.f" :style="{ bottom: tk.pct + '%' }">{{ tk.f ? (tk.f / 1000) + 'k' : '0' }}</span>
        </div>
        <div class="plot">
          <img :src="blobUrl(res.spectrogram.blob)" alt="" draggable="false" />
          <div class="grid-h" v-for="tk in ticks" :key="'g' + tk.f" :style="{ bottom: tk.pct + '%' }" />
          <div v-if="res.cutoffHz" class="cut" :style="{ bottom: (res.cutoffHz / res.nyquistHz) * 100 + '%' }">
            <span>{{ khz(res.cutoffHz) }}</span>
          </div>
        </div>
        <div class="xaxis">
          <span v-for="tk in timeTicks" :key="tk.s" :style="{ left: tk.pct + '%' }">{{ duration(tk.s) }}</span>
        </div>
        <figcaption>
          <span>{{ t('q.freq') }} (Hz) ↑</span>
          <span>{{ t('q.time') }} →</span>
        </figcaption>
      </figure>
      <p class="disclaimer">{{ t('q.disclaimer') }}</p>
    </template>
  </div>
  <p v-else class="muted">{{ t('q.single') }}</p>
</template>

<style scoped>
.quality { max-width: 1100px; }
.intro { display: flex; align-items: center; gap: 16px; justify-content: space-between; margin-bottom: 18px; }
.intro p { margin: 0; color: var(--muted); max-width: 640px; line-height: 1.6; }
.verdict { display: flex; gap: 14px; align-items: flex-start; padding: 16px 18px; border-radius: var(--radius); border: 1px solid var(--border); background: var(--surface); }
.verdict > svg { width: 28px; height: 28px; flex: none; margin-top: 2px; }
.verdict h3 { margin: 0 0 4px; font-size: 16px; }
.verdict p { margin: 0; color: var(--text-2); line-height: 1.6; }
.verdict.good > svg { color: var(--success); }
.verdict.good { background: linear-gradient(135deg, var(--success-soft), transparent 60%), var(--surface); }
.verdict.bad > svg { color: var(--danger); }
.verdict.bad { background: linear-gradient(135deg, var(--danger-soft), transparent 60%), var(--surface); }
.verdict.warn > svg { color: var(--warning); }
.verdict.warn { background: linear-gradient(135deg, var(--warning-soft), transparent 60%), var(--surface); }
.verdict.neutral > svg { color: var(--info); }
.stats { display: flex; flex-wrap: wrap; gap: 10px; margin: 14px 0 18px; }
.stat { padding: 10px 14px; border-radius: 10px; background: var(--surface); border: 1px solid var(--border); display: flex; flex-direction: column; gap: 2px; min-width: 120px; }
.stat span { font-size: 11.5px; color: var(--muted); }
.stat b { font-size: 15px; }
.spectro { margin: 0; display: grid; grid-template-columns: 44px 1fr; grid-template-rows: auto 22px auto; }
.yaxis { position: relative; grid-row: 1; }
.yaxis span { position: absolute; right: 8px; transform: translateY(50%); font-size: 10.5px; color: var(--muted); font-variant-numeric: tabular-nums; }
.plot { position: relative; grid-row: 1; grid-column: 2; border-radius: 10px; overflow: hidden; background: #000; box-shadow: 0 0 0 1px var(--border); }
.plot img { width: 100%; aspect-ratio: 1600 / 600; object-fit: fill; display: block; image-rendering: auto; }
.grid-h { position: absolute; left: 0; right: 0; height: 1px; background: rgba(255,255,255,.12); }
.cut { position: absolute; left: 0; right: 0; height: 0; border-top: 1.5px dashed #fbbf24; }
.cut span { position: absolute; right: 8px; bottom: 3px; font-size: 11px; font-weight: 700; color: #111; background: #fbbf24; padding: 1px 6px; border-radius: 5px; }
.xaxis { position: relative; grid-row: 2; grid-column: 2; }
.xaxis span { position: absolute; top: 4px; transform: translateX(-50%); font-size: 10.5px; color: var(--muted); }
.xaxis span:first-child { transform: none; }
figcaption { grid-column: 2; display: flex; justify-content: space-between; font-size: 11px; color: var(--faint); margin-top: 2px; }
.disclaimer { font-size: 12px; color: var(--faint); margin-top: 14px; }
</style>
