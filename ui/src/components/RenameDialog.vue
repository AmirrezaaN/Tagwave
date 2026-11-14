<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { ArrowRight, LoaderCircle, Info } from '@lucide/vue'
import Modal from './Modal.vue'
import { state, selectedFiles, closeDialog, upsertFiles, toast, updateSettings, setField } from '../lib/store.js'
import { call } from '../lib/api.js'
import { t, errorText } from '../lib/i18n.js'

const tab = ref('rename')
const files = computed(() => selectedFiles.value)
const pattern = ref(state.settings.renamePattern || '{track} - {artist} - {title}')
const parsePattern = ref(state.settings.parsePattern || '{artist} - {title}')
const preview = ref([])
const parsed = ref([])
const error = ref('')
const busy = ref(false)
const input = ref(null)
const parseInput = ref(null)

const TOKENS = ['title', 'artist', 'album', 'albumartist', 'track', 'tracktotal', 'disc', 'year', 'genre', 'composer', 'filename']
const PARSE_TOKENS = ['artist', 'title', 'album', 'albumartist', 'track', 'disc', 'date', 'genre', 'composer', 'skip']
const tokenLabel = (k) => ({ year: t('rn.year'), filename: t('rn.filename'), skip: '{skip}', tracktotal: t('rn.tracktotal'), disctotal: t('rn.disctotal') }[k] || t('f.' + k))
const history = computed(() => state.settings.renameHistory || [])

function insert(tok, which) {
  const el = which === 'parse' ? parseInput.value : input.value
  const model = which === 'parse' ? parsePattern : pattern
  const s = el?.selectionStart ?? model.value.length
  const e = el?.selectionEnd ?? s
  model.value = model.value.slice(0, s) + '{' + tok + '}' + model.value.slice(e)
  requestAnimationFrame(() => { el?.focus(); const p = s + tok.length + 2; el?.setSelectionRange(p, p) })
}

let timer
function refresh() {
  clearTimeout(timer)
  timer = setTimeout(async () => {
    error.value = ''
    try {
      if (tab.value === 'rename') {
        const items = files.value.map((f) => ({ id: f.id, fields: state.drafts[f.id]?.fields }))
        preview.value = await call('rename.preview', { items, pattern: pattern.value })
      } else {
        parsed.value = await call('tags.fromFilename', { ids: files.value.map((f) => f.id), pattern: parsePattern.value })
      }
    } catch (e) {
      error.value = errorText(e)
      preview.value = []
      parsed.value = []
    }
  }, 150)
}
watch([pattern, parsePattern, tab], refresh)
onMounted(refresh)

const ready = computed(() => preview.value.filter((p) => p.status === 'ok').length)
const parsedOk = computed(() => parsed.value.filter((p) => p.fields).length)

async function applyRename() {
  busy.value = true
  try {
    const items = files.value.map((f) => ({ id: f.id, fields: state.drafts[f.id]?.fields }))
    const res = await call('rename.apply', { items, pattern: pattern.value })
    upsertFiles(res.files)
    const n = res.results.filter((r) => r.ok && r.newPath !== r.path).length
    const failed = res.results.filter((r) => !r.ok)
    toast(t('t.renamed', { n }), 'success')
    if (failed.length) toast(errorText({ code: failed[0].error }), 'error')
    updateSettings({}).catch(() => {})
    state.settings.renamePattern = pattern.value
    closeDialog()
  } catch (e) {
    toast(errorText(e), 'error')
  } finally { busy.value = false }
}

function applyParse() {
  let n = 0
  for (const p of parsed.value) {
    if (!p.fields) continue
    for (const [k, v] of Object.entries(p.fields)) setField([p.id], k, v)
    n++
  }
  state.settings.parsePattern = parsePattern.value
  toast(t('t.parsed', { n }), 'success')
  closeDialog()
}
const nameOf = (id) => files.value.find((f) => f.id === id)?.name || ''
</script>

<template>
  <Modal :title="t('rn.title')" width="860px" @close="closeDialog">
    <div class="tabs">
      <button :class="{ on: tab === 'rename' }" @click="tab = 'rename'">{{ t('rn.tabRename') }}</button>
      <button :class="{ on: tab === 'parse' }" @click="tab = 'parse'">{{ t('rn.tabParse') }}</button>
    </div>

    <template v-if="tab === 'rename'">
      <label class="label">{{ t('rn.pattern') }}</label>
      <div class="prow">
        <input ref="input" class="input mono" v-model="pattern" dir="ltr" spellcheck="false" autofocus />
        <select class="select hist" v-if="history.length" @change="pattern = $event.target.value; $event.target.value = ''">
          <option value="">↺</option>
          <option v-for="h in history" :key="h" :value="h">{{ h }}</option>
        </select>
      </div>
      <div class="tokens">
        <span class="muted">{{ t('rn.insert') }}:</span>
        <button v-for="k in TOKENS" :key="k" class="tok" @click="insert(k)">{{ tokenLabel(k) }}</button>
      </div>
      <p class="note"><Info /> {{ t('rn.unsaved') }}</p>
      <div v-if="error" class="err">{{ error }}</div>
      <div class="table">
        <div v-for="p in preview" :key="p.id" class="tr">
          <span class="old ellipsis">{{ nameOf(p.id) }}</span>
          <ArrowRight class="flip-rtl arrow" />
          <span class="new ellipsis" :class="{ same: p.status === 'same' }">{{ p.newName }}</span>
          <span class="badge" :class="{ lossless: p.status === 'ok', danger: ['conflict', 'exists', 'empty'].includes(p.status) }">{{ t('rn.s.' + p.status) }}</span>
        </div>
      </div>
    </template>

    <template v-else>
      <label class="label">{{ t('rn.parse') }}</label>
      <input ref="parseInput" class="input mono" v-model="parsePattern" dir="ltr" spellcheck="false" />
      <div class="tokens">
        <span class="muted">{{ t('rn.insert') }}:</span>
        <button v-for="k in PARSE_TOKENS" :key="k" class="tok" @click="insert(k, 'parse')">{{ tokenLabel(k) }}</button>
      </div>
      <p class="note"><Info /> {{ t('rn.parseHint') }}</p>
      <div v-if="error" class="err">{{ error }}</div>
      <div class="table">
        <div v-for="p in parsed" :key="p.id" class="tr parse">
          <span class="old ellipsis">{{ nameOf(p.id) }}</span>
          <ArrowRight class="flip-rtl arrow" />
          <span v-if="p.fields" class="fields">
            <span v-for="(v, k) in p.fields" :key="k" class="kv"><i>{{ t('f.' + k) }}</i> <b dir="auto">{{ v }}</b></span>
          </span>
          <span v-else class="badge danger">{{ t('rn.noMatch') }}</span>
        </div>
      </div>
    </template>

    <template #footer>
      <button class="btn" @click="closeDialog">{{ t('a.cancel') }}</button>
      <button v-if="tab === 'rename'" class="btn primary" :disabled="!ready || busy" @click="applyRename">
        <LoaderCircle v-if="busy" class="spin" /> {{ t('rn.apply', { n: ready }) }}
      </button>
      <button v-else class="btn primary" :disabled="!parsedOk" @click="applyParse">{{ t('rn.parseApply', { n: parsedOk }) }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.tabs { display: flex; gap: 4px; background: var(--surface-2); padding: 3px; border-radius: 10px; border: 1px solid var(--border); margin-bottom: 16px; }
.tabs button { flex: 1; height: 32px; border: 0; background: transparent; border-radius: 7px; color: var(--muted); font-weight: 600; }
.tabs button.on { background: var(--surface-3); color: var(--text); }
.prow { display: flex; gap: 8px; }
.hist { width: 64px; flex: none; }
.mono { font-family: var(--mono); font-size: 13px; }
.tokens { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0; align-items: center; font-size: 12px; }
.tok { height: 26px; padding: 0 9px; border-radius: 13px; border: 1px solid var(--border); background: var(--surface-2); font-size: 12px; color: var(--text-2); }
.tok:hover { border-color: var(--primary); color: var(--primary); }
.note { display: flex; align-items: center; gap: 6px; color: var(--muted); font-size: 12px; margin: 4px 0 12px; }
.note svg { width: 14px; height: 14px; flex: none; }
.err { color: var(--danger); font-size: 12.5px; margin-bottom: 10px; }
.table { border: 1px solid var(--border); border-radius: 12px; max-height: 340px; overflow: auto; }
.tr { display: grid; grid-template-columns: minmax(0, 1fr) 18px minmax(0, 1.2fr) auto; gap: 10px; align-items: center; padding: 8px 12px; border-bottom: 1px solid var(--border); font-size: 12.5px; }
.tr:last-child { border-bottom: 0; }
.tr.parse { grid-template-columns: minmax(0, 1fr) 18px minmax(0, 1.6fr); }
.old { color: var(--muted); }
.new { font-weight: 600; }
.new.same { color: var(--muted); font-weight: 400; }
.arrow { width: 14px; height: 14px; color: var(--faint); }
.fields { display: flex; flex-wrap: wrap; gap: 6px; }
.kv { background: var(--surface-2); border: 1px solid var(--border); border-radius: 7px; padding: 2px 8px; }
.kv i { font-style: normal; color: var(--muted); font-size: 11px; }
</style>
