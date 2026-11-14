<script setup>
import { ref, computed, onMounted, watch, onBeforeUnmount } from 'vue'
import { ShieldCheck, Copy, TriangleAlert, CircleCheck, CircleAlert, FolderOpen, LoaderCircle, BadgeCheck, Waves, Minus, ArrowRight } from '@lucide/vue'
import Modal from './Modal.vue'
import { state, selectedFiles, closeDialog, updateSettings, confirmDialog, toast } from '../lib/store.js'
import { call, onEvent, waitJob } from '../lib/api.js'
import { t, errorText } from '../lib/i18n.js'
import { khz } from '../lib/format.js'

const LOSSLESS = ['flac', 'alac', 'wav', 'aiff']
const LOSSY = ['mp3', 'aac', 'opus', 'ogg']
const LABEL = { flac: 'FLAC', alac: 'ALAC', wav: 'WAV', aiff: 'AIFF', mp3: 'MP3', aac: 'AAC', opus: 'Opus', ogg: 'OGG' }

const files = computed(() => selectedFiles.value)
const ex = state.settings.export || {}
const target = ref(ex.target || 'flac')
const qualities = ref({ ...(ex.quality || {}) })
const outputMode = ref(ex.outputMode || 'same')
const outputDir = ref(ex.outputDir || '')
const overwrite = ref(ex.overwrite || 'rename')
const flacLevel = ref(ex.flacLevel ?? 8)
const addToList = ref(!!ex.addToList)
const plan = ref([])
const planning = ref(false)
const phase = ref('setup')    // setup | running | done
const progress = ref({})
const results = ref([])
const jobId = ref(null)
const overall = ref(0)

const qualityOptions = computed(() => state.info.targets?.[target.value]?.qualities || [])
const quality = computed({
  get: () => qualities.value[target.value] || qualityOptions.value[0],
  set: (v) => { qualities.value[target.value] = v },
})
const options = computed(() => ({
  target: target.value, quality: quality.value || null, outputMode: outputMode.value, outputDir: outputDir.value,
  overwrite: overwrite.value, flacLevel: flacLevel.value, addToList: addToList.value,
}))

let timer
async function refreshPlan() {
  clearTimeout(timer)
  timer = setTimeout(async () => {
    if (outputMode.value === 'custom' && !outputDir.value) { plan.value = []; return }
    planning.value = true
    try {
      plan.value = await call('convert.plan', { ids: files.value.map((f) => f.id), options: options.value })
    } catch (e) {
      plan.value = []
      if (e.code !== 'no-output-dir') toast(errorText(e), 'error')
    } finally { planning.value = false }
  }, 120)
}
watch(options, refreshPlan, { deep: true })
onMounted(refreshPlan)

const planById = computed(() => Object.fromEntries(plan.value.map((p) => [p.id, p])))
const modeOf = (p) => {
  if (!p || p.error) return 'error'
  const m = p.plan.mode
  if (m === 'lossless') return p.plan.bitPerfect ? 'lossless-bp' : 'lossless'
  return m
}
const counts = computed(() => {
  const c = {}
  for (const p of plan.value) { const m = modeOf(p); c[m] = (c[m] || 0) + 1 }
  return c
})
const anyLossy = computed(() => plan.value.some((p) => p.plan?.mode === 'lossy'))
const warnText = (w, p) => {
  if (w.startsWith('custom-dropped:')) return w
  return t('ex.w.' + w, { rate: khz(p?.plan?.sampleRate) })
}

async function chooseDir() {
  try {
    const r = await call('dialog.pickFolder', { initial: outputDir.value })
    if (r.path) { outputDir.value = r.path; outputMode.value = 'custom' }
  } catch (e) {
    if (e.code === 'no-native') {
      const v = prompt('Folder path:', outputDir.value)
      if (v) { outputDir.value = v; outputMode.value = 'custom' }
    } else toast(errorText(e), 'error')
  }
}

let off = null
onBeforeUnmount(() => off?.())

async function start() {
  if (anyLossy.value && state.settings.confirmLossy) {
    const ok = await confirmDialog({
      title: t('ex.confirmTitle'), body: t('ex.confirmBody'),
      buttons: [{ label: t('a.cancel'), value: false }, { label: t('ex.continue'), value: true, kind: 'primary' }],
    })
    if (!ok) return
  }
  updateSettings({ export: { target: target.value, quality: qualities.value, outputMode: outputMode.value,
    outputDir: outputDir.value, overwrite: overwrite.value, flacLevel: flacLevel.value, addToList: addToList.value } }).catch(() => {})
  const items = files.value.map((f) => {
    const d = state.drafts[f.id]
    return { id: f.id, fields: d.fields, custom: d.custom, pictures: d.pictures.map((p) => ({ blob: p.blob, type: p.type, desc: p.desc || '' })) }
  })
  phase.value = 'running'
  progress.value = {}
  off = onEvent((msg) => {
    if (msg.type === 'convert.item' && msg.data.jobId === jobId.value) progress.value[msg.data.index] = msg.data
    if (msg.type === 'job' && msg.data.id === jobId.value) overall.value = msg.data.progress
  })
  try {
    const res = await call('convert.start', { items, options: options.value })
    jobId.value = res.jobId
    const job = await waitJob(res.jobId)
    results.value = job.result?.results || []
    phase.value = 'done'
  } catch (e) {
    toast(errorText(e), 'error')
    phase.value = 'setup'
  }
}
function cancel() { if (jobId.value) call('jobs.cancel', { id: jobId.value }) }
const summary = computed(() => {
  const s = { done: 0, error: 0, skipped: 0, cancelled: 0, verified: 0 }
  for (const r of results.value) { if (!r) continue; s[r.state] = (s[r.state] || 0) + 1; if (r.verified) s.verified++ }
  return s
})
function reveal() {
  const r = results.value.find((x) => x?.state === 'done')
  if (r) call('system.reveal', { path: r.path })
}
const nameOf = (id) => files.value.find((f) => f.id === id)?.name || id
const baseName = (p) => (p || '').split(/[\\/]/).pop()
</script>

<template>
  <Modal :title="t('ex.title')" :subtitle="t('ex.sub', { n: files.length })" width="880px" :closable="phase !== 'running'" @close="closeDialog">
    <div v-if="phase === 'setup'" class="setup">
      <div class="formats">
        <div class="fgroup">
          <div class="ghead"><ShieldCheck /> {{ t('ex.lossless') }}</div>
          <div class="cards">
            <button v-for="k in LOSSLESS" :key="k" class="fcard" :class="{ on: target === k }" @click="target = k">
              <b>{{ LABEL[k] }}</b><span>{{ t('ex.t.' + k) }}</span>
            </button>
          </div>
        </div>
        <div class="fgroup">
          <div class="ghead lossy"><Waves /> {{ t('ex.lossy') }}</div>
          <div class="cards">
            <button v-for="k in LOSSY" :key="k" class="fcard" :class="{ on: target === k }" @click="target = k">
              <b>{{ LABEL[k] }}</b><span>{{ t('ex.t.' + k) }}</span>
            </button>
          </div>
        </div>
      </div>

      <div class="opts">
        <div v-if="qualityOptions.length">
          <label class="label">{{ t('ex.quality') }}</label>
          <select class="select" v-model="quality">
            <option v-for="q in qualityOptions" :key="q" :value="q">{{ t('ex.qn.' + q) }}</option>
          </select>
        </div>
        <div v-if="target === 'flac'">
          <label class="label">{{ t('ex.flacLevel') }} · <span class="ltr">{{ flacLevel }}</span></label>
          <input type="range" min="0" max="8" v-model.number="flacLevel" class="range" />
          <div class="hint">{{ t('ex.flacHint') }}</div>
        </div>
        <div>
          <label class="label">{{ t('ex.output') }}</label>
          <div class="radio"><label class="check"><input type="radio" value="same" v-model="outputMode" /> {{ t('ex.same') }}</label></div>
          <div class="radio dir">
            <label class="check"><input type="radio" value="custom" v-model="outputMode" /> {{ t('ex.custom') }}</label>
            <input class="input sm" :value="outputDir" readonly dir="ltr" :placeholder="t('ex.choose')" @click="chooseDir" />
            <button class="btn sm" @click="chooseDir"><FolderOpen /></button>
          </div>
        </div>
        <div>
          <label class="label">{{ t('ex.exists') }}</label>
          <select class="select" v-model="overwrite">
            <option value="rename">{{ t('ex.rename') }}</option>
            <option value="skip">{{ t('ex.skip') }}</option>
            <option value="overwrite">{{ t('ex.overwrite') }}</option>
          </select>
          <label class="check add"><input type="checkbox" v-model="addToList" /> {{ t('ex.addToList') }}</label>
        </div>
      </div>

      <div class="plan">
        <div class="plan-head">
          <span class="label">{{ t('ex.plan') }}</span>
          <LoaderCircle v-if="planning" class="spin small-ico" />
          <span class="chips">
            <span v-if="counts['copy-file']" class="badge lossless"><Copy /> {{ counts['copy-file'] }} · {{ t('ex.m.copy-file') }}</span>
            <span v-if="counts.remux" class="badge lossless"><Copy /> {{ counts.remux }} · {{ t('ex.m.remux') }}</span>
            <span v-if="counts['lossless-bp']" class="badge lossless"><BadgeCheck /> {{ counts['lossless-bp'] }} · {{ t('ex.m.lossless-bp') }}</span>
            <span v-if="counts.lossless" class="badge info"><ShieldCheck /> {{ counts.lossless }} · {{ t('ex.m.lossless') }}</span>
            <span v-if="counts.lossy" class="badge lossy"><TriangleAlert /> {{ counts.lossy }} · {{ t('ex.m.lossy') }}</span>
            <span v-if="counts.unsupported || counts.error" class="badge danger"><CircleAlert /> {{ (counts.unsupported || 0) + (counts.error || 0) }}</span>
          </span>
        </div>
        <div class="plan-list">
          <div v-for="f in files.slice(0, 200)" :key="f.id" class="pitem">
            <div class="pname ellipsis">{{ f.name }}</div>
            <template v-if="planById[f.id]">
              <div class="pmode" :class="modeOf(planById[f.id])">
                <template v-if="planById[f.id].error">{{ errorText(planById[f.id].error) }}</template>
                <template v-else>
                  {{ t('ex.m.' + modeOf(planById[f.id])) }}
                  <span class="arrow"><ArrowRight class="flip-rtl" /> {{ baseName(planById[f.id].output) }}</span>
                  <span v-if="planById[f.id].action === 'skip'" class="muted">({{ t('ex.skip') }})</span>
                </template>
              </div>
              <ul v-if="planById[f.id].plan?.warnings?.length" class="warns">
                <li v-for="w in planById[f.id].plan.warnings" :key="w" :class="{ strong: w === 'lossy-to-lossy' }">{{ warnText(w, planById[f.id]) }}</li>
              </ul>
            </template>
            <div v-else class="pmode muted"><Minus /></div>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="run">
      <div class="overall">
        <div class="ohead">
          <b>{{ phase === 'running' ? t('ex.running') : t('ex.doneTitle') }}</b>
          <span v-if="phase === 'running'" class="ltr muted">{{ Math.round(overall * 100) }}%</span>
          <span v-else class="chips">
            <span class="badge lossless" v-if="summary.done"><CircleCheck /> {{ t('ex.ok', { n: summary.done }) }}</span>
            <span class="badge primary" v-if="summary.verified"><BadgeCheck /> {{ t('ex.verified') }} ×{{ summary.verified }}</span>
            <span class="badge" v-if="summary.skipped">{{ t('ex.skipped', { n: summary.skipped }) }}</span>
            <span class="badge danger" v-if="summary.error"><CircleAlert /> {{ t('ex.failed', { n: summary.error }) }}</span>
          </span>
        </div>
        <div class="track"><div class="fill" :style="{ width: (phase === 'done' ? 100 : overall * 100) + '%' }" /></div>
      </div>
      <div class="plan-list">
        <div v-for="(f, i) in files" :key="f.id" class="pitem">
          <div class="pname ellipsis">{{ f.name }}</div>
          <div class="pmode">
            <template v-if="results[i]">
              <span v-if="results[i].state === 'done'" class="ok"><CircleCheck /> {{ baseName(results[i].path) }}
                <span v-if="results[i].verified" class="badge primary"><BadgeCheck /> {{ t('ex.verified') }}</span></span>
              <span v-else-if="results[i].state === 'error'" class="err"><CircleAlert /> {{ errorText(results[i].error) }}</span>
              <span v-else class="muted">{{ results[i].state === 'skipped' ? t('ex.skip') : t('e.cancelled') }}</span>
            </template>
            <div v-else class="mini"><div :style="{ width: ((progress[i]?.progress || 0) * 100) + '%' }" /></div>
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <template v-if="phase === 'setup'">
        <span v-if="anyLossy" class="foot-warn"><TriangleAlert /> {{ t('ex.m.lossy') }}</span>
        <button class="btn" @click="closeDialog">{{ t('a.cancel') }}</button>
        <button class="btn gradient" :disabled="!plan.length || planning || (outputMode === 'custom' && !outputDir)" @click="start">
          {{ files.length === 1 ? t('ex.startOne') : t('ex.start', { n: files.length }) }}
        </button>
      </template>
      <template v-else-if="phase === 'running'">
        <button class="btn" @click="cancel">{{ t('a.cancel') }}</button>
      </template>
      <template v-else>
        <button class="btn" v-if="summary.done" @click="reveal"><FolderOpen /> {{ t('ex.showFolder') }}</button>
        <button class="btn primary" @click="closeDialog">{{ t('a.done') }}</button>
      </template>
    </template>
  </Modal>
</template>

<style scoped>
.formats { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.ghead { display: flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 650; color: var(--success); margin-bottom: 8px; }
.ghead.lossy { color: var(--warning); }
.ghead svg { width: 14px; height: 14px; }
.cards { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.fcard { text-align: start; padding: 10px 12px; border-radius: 11px; border: 1px solid var(--border); background: var(--surface-2); display: flex; flex-direction: column; gap: 2px; transition: .15s; }
.fcard:hover { border-color: var(--border-strong); background: var(--surface-3); }
.fcard.on { border-color: var(--primary); background: var(--primary-soft); box-shadow: 0 0 0 3px var(--primary-soft); }
.fcard b { font-size: 14px; }
.fcard span { font-size: 11.5px; color: var(--muted); }
.opts { display: grid; grid-template-columns: 1fr 1.4fr 1fr; gap: 18px; margin: 18px 0; align-items: start; }
.opts > div:first-child:last-child { grid-column: span 3; }
.hint { font-size: 11px; color: var(--faint); margin-top: 4px; line-height: 1.4; }
.range { width: 100%; accent-color: var(--primary); }
.radio { margin-bottom: 6px; }
.radio.dir { display: flex; align-items: center; gap: 6px; }
.radio.dir .input { height: 30px; font-size: 12px; cursor: pointer; }
.check.add { margin-top: 10px; font-size: 12.5px; }
.plan { border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
.plan-head { display: flex; align-items: center; gap: 10px; padding: 10px 12px; background: var(--surface-2); border-bottom: 1px solid var(--border); flex-wrap: wrap; }
.plan-head .label { margin: 0; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.small-ico { width: 14px; height: 14px; color: var(--muted); }
.plan-list { max-height: 240px; overflow: auto; }
.pitem { padding: 9px 12px; border-bottom: 1px solid var(--border); display: grid; grid-template-columns: minmax(160px, 34%) 1fr; gap: 4px 12px; }
.pitem:last-child { border-bottom: 0; }
.pname { font-weight: 550; font-size: 12.5px; }
.pmode { font-size: 12.5px; color: var(--text-2); display: flex; align-items: center; gap: 6px; flex-wrap: wrap; min-width: 0; }
.pmode svg { width: 14px; height: 14px; }
.pmode.copy-file, .pmode.remux, .pmode.lossless-bp { color: var(--success); }
.pmode.lossy { color: var(--warning); }
.pmode.error, .pmode.unsupported { color: var(--danger); }
.arrow { color: var(--muted); display: inline-flex; align-items: center; gap: 4px; }
.warns { grid-column: 2; margin: 0; padding-inline-start: 16px; font-size: 11.5px; color: var(--muted); }
.warns li.strong { color: var(--warning); }
.foot-warn { margin-inline-end: auto; display: flex; align-items: center; gap: 6px; color: var(--warning); font-size: 12.5px; }
.foot-warn svg { width: 15px; height: 15px; }
.overall { margin-bottom: 14px; }
.ohead { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; gap: 10px; }
.track { height: 6px; border-radius: 6px; background: var(--surface-3); overflow: hidden; }
.fill { height: 100%; background: var(--grad); transition: width .2s; }
.run .plan-list { max-height: 380px; border: 1px solid var(--border); border-radius: 12px; }
.mini { width: 100%; max-width: 260px; height: 4px; border-radius: 4px; background: var(--surface-3); overflow: hidden; }
.mini div { height: 100%; background: var(--primary); transition: width .2s; }
.ok { color: var(--success); display: inline-flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.err { color: var(--danger); display: inline-flex; align-items: center; gap: 6px; }
.input.sm { height: 30px; }
</style>
