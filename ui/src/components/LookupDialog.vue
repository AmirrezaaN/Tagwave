<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { Search, LoaderCircle, Music, Check, ImageDown, Globe, CircleAlert } from '@lucide/vue'
import Modal from './Modal.vue'
import { state, editableSelection, closeDialog, toast, setField, setFrontCover } from '../lib/store.js'
import { call, waitJob, blobUrl } from '../lib/api.js'
import { t, errorText } from '../lib/i18n.js'
import { dims, size } from '../lib/format.js'

const PROVIDERS = { musicbrainz: 'MusicBrainz', itunes: 'iTunes', deezer: 'Deezer' }
const FIELDS = ['title', 'artist', 'album', 'albumartist', 'date', 'genre', 'track', 'tracktotal', 'disc', 'disctotal', 'isrc']
const id = computed(() => editableSelection.value[0])
const draft = computed(() => state.drafts[id.value]?.fields || {})
const q = reactive({ artist: '', title: '', album: '' })
const providers = ref([...(state.settings.onlineProviders || Object.keys(PROVIDERS))])
const busy = ref(false)
const results = ref([])
const errors = ref([])
const searched = ref(false)
const filter = ref('all')
const current = ref(null)
const checks = reactive({})
const cover = ref(null)
const coverBusy = ref('')

onMounted(() => {
  q.artist = draft.value.artist || ''
  q.title = draft.value.title || ''
  q.album = draft.value.title ? '' : draft.value.album || ''
  if (state.settings.onlineEnabled && (q.artist || q.title || q.album)) search()
})

async function search() {
  if (!state.settings.onlineEnabled) return
  busy.value = true
  searched.value = true
  current.value = null
  try {
    const { jobId } = await call('online.search', { ...q, providers: providers.value })
    const job = await waitJob(jobId)
    results.value = job.result.results
    errors.value = job.result.errors
    if (results.value.length) pick(results.value[0])
  } catch (e) {
    toast(errorText(e), 'error')
  } finally { busy.value = false }
}
const shown = computed(() => (filter.value === 'all' ? results.value : results.value.filter((r) => r.provider === filter.value)))

async function pick(r) {
  current.value = r
  cover.value = null
  if (r.needsDetails && !r.detailsLoaded) {
    try {
      Object.assign(r, await call('online.details', { provider: r.provider, id: r.id }))
      r.detailsLoaded = true
    } catch { /* ignore */ }
  }
  for (const f of FIELDS) checks[f] = !!(r[f] && String(r[f]) !== String(draft.value[f] || ''))
}

async function useCover(c) {
  coverBusy.value = c.url
  try {
    cover.value = await call('images.fetch', { url: c.url })
  } catch (e) {
    toast(errorText(e), 'error')
  } finally { coverBusy.value = '' }
}

function apply() {
  const r = current.value
  if (!r) return
  for (const f of FIELDS) if (checks[f] && r[f]) setField([id.value], f, String(r[f]))
  if (cover.value) setFrontCover([id.value], cover.value)
  toast(t('t.applied'), 'success')
  closeDialog()
}
const anyChecked = computed(() => FIELDS.some((f) => checks[f]) || !!cover.value)
</script>

<template>
  <Modal :title="t('lk.title')" width="1000px" body-class="lk-body" @close="closeDialog">
    <div v-if="!state.settings.onlineEnabled" class="off"><Globe /> {{ t('lk.disabled') }}</div>
    <template v-else>
      <form class="q" @submit.prevent="search">
        <input class="input" v-model="q.artist" :placeholder="t('f.artist')" dir="auto" autofocus />
        <input class="input" v-model="q.title" :placeholder="t('f.title')" dir="auto" />
        <input class="input" v-model="q.album" :placeholder="t('f.album')" dir="auto" />
        <button class="btn primary" :disabled="busy"><LoaderCircle v-if="busy" class="spin" /><Search v-else /> {{ t('lk.search') }}</button>
      </form>
      <div class="srcs">
        <span class="muted">{{ t('lk.sources') }}:</span>
        <label v-for="(name, k) in PROVIDERS" :key="k" class="check"><input type="checkbox" :value="k" v-model="providers" /> {{ name }}</label>
        <span class="faint note">{{ t('lk.note') }}</span>
      </div>
      <div v-for="e in errors" :key="e.provider" class="perr"><CircleAlert /> {{ t('lk.providerFail', { p: PROVIDERS[e.provider] }) }} — {{ errorText({ code: 'online-' + e.code }) }}</div>

      <div class="split">
        <div class="results">
          <div class="filters" v-if="results.length">
            <button :class="{ on: filter === 'all' }" @click="filter = 'all'">{{ t('lk.all') }} · {{ results.length }}</button>
            <button v-for="(name, k) in PROVIDERS" :key="k" :class="{ on: filter === k }" @click="filter = k"
                    v-show="results.some((r) => r.provider === k)">{{ name }}</button>
          </div>
          <div class="rlist">
            <div v-if="busy" class="empty"><LoaderCircle class="spin" /> {{ t('lk.searching') }}</div>
            <div v-else-if="searched && !results.length" class="empty">{{ t('lk.none') }}</div>
            <button v-for="r in shown" :key="r.provider + r.id" class="ritem" :class="{ on: current === r }" @click="pick(r)">
              <span class="rthumb">
                <img v-if="r.thumb" :src="r.thumb" alt="" loading="lazy" referrerpolicy="no-referrer" @error="$event.target.style.display = 'none'" />
                <Music />
              </span>
              <span class="rtext">
                <b class="ellipsis bidi">{{ r.title }}</b>
                <span class="ellipsis bidi">{{ r.artist }}</span>
                <span class="ellipsis faint bidi">{{ [r.album, (r.date || '').slice(0, 4)].filter(Boolean).join(' · ') }}</span>
              </span>
              <span class="prov">{{ PROVIDERS[r.provider] }}</span>
            </button>
          </div>
        </div>

        <div class="detail">
          <div v-if="!current" class="empty">{{ t('lk.pick') }}</div>
          <template v-else>
            <table class="cmp">
              <thead><tr><th></th><th>{{ t('lk.current') }}</th><th>{{ t('lk.found') }}</th></tr></thead>
              <tbody>
                <tr v-for="f in FIELDS" :key="f" v-show="current[f]" :class="{ on: checks[f] }">
                  <td><label class="check"><input type="checkbox" v-model="checks[f]" /> {{ f.endsWith('total') ? t('rn.' + f) : t('f.' + f) }}</label></td>
                  <td class="cur" dir="auto">{{ draft[f] || '—' }}</td>
                  <td class="new" dir="auto">{{ current[f] }}</td>
                </tr>
              </tbody>
            </table>
            <div class="covers" v-if="current.covers?.length">
              <div class="label">{{ t('lk.cover') }}</div>
              <div class="crow">
                <div class="cthumb">
                  <img v-if="cover" :src="blobUrl(cover.blob)" alt="" />
                  <img v-else-if="current.thumb" :src="current.thumb" alt="" referrerpolicy="no-referrer" @error="$event.target.style.display = 'none'" />
                </div>
                <div class="cacts">
                  <button v-for="c in current.covers" :key="c.url" class="btn sm" :disabled="!!coverBusy" @click="useCover(c)">
                    <LoaderCircle v-if="coverBusy === c.url" class="spin" /><ImageDown v-else /> {{ t('lk.useCover') }}
                  </button>
                  <div v-if="cover" class="cinfo ltr"><Check /> {{ cover.mime === 'image/png' ? 'PNG' : 'JPEG' }} · {{ dims(cover.width, cover.height) }} · {{ size(cover.size) }}</div>
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>
    </template>
    <template #footer>
      <button class="btn" @click="closeDialog">{{ t('a.cancel') }}</button>
      <button class="btn primary" :disabled="!anyChecked" @click="apply">{{ t('lk.apply') }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.off { display: flex; align-items: center; gap: 10px; padding: 30px; justify-content: center; color: var(--muted); }
.off svg { width: 20px; height: 20px; }
.q { display: grid; grid-template-columns: 1fr 1fr 1fr auto; gap: 8px; }
.srcs { display: flex; align-items: center; gap: 14px; margin: 10px 0; font-size: 12.5px; flex-wrap: wrap; }
.note { margin-inline-start: auto; font-size: 11.5px; }
.perr { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--warning); margin-bottom: 6px; }
.perr svg { width: 14px; height: 14px; }
.split { display: grid; grid-template-columns: 380px 1fr; gap: 14px; height: 430px; }
.results { display: flex; flex-direction: column; min-height: 0; border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
.filters { display: flex; gap: 4px; padding: 6px; border-bottom: 1px solid var(--border); background: var(--surface-2); }
.filters button { height: 26px; padding: 0 10px; border-radius: 7px; border: 0; background: transparent; color: var(--muted); font-size: 12px; font-weight: 600; }
.filters button.on { background: var(--surface-3); color: var(--text); }
.rlist { overflow: auto; flex: 1; padding: 4px; }
.ritem { width: 100%; display: flex; align-items: center; gap: 10px; padding: 7px 8px; border: 0; background: transparent; border-radius: 9px; text-align: start; }
.ritem:hover { background: var(--hover); }
.ritem.on { background: var(--active); }
.rthumb { width: 44px; height: 44px; flex: none; border-radius: 6px; overflow: hidden; background: var(--surface-3); display: grid; place-items: center; color: var(--faint); position: relative; }
.rthumb img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.rthumb svg { width: 18px; height: 18px; }
.rtext { flex: 1; min-width: 0; display: flex; flex-direction: column; font-size: 12px; }
.rtext b { font-size: 13px; }
.prov { font-size: 10.5px; color: var(--muted); background: var(--surface-3); padding: 2px 6px; border-radius: 5px; }
.detail { overflow: auto; border: 1px solid var(--border); border-radius: 12px; padding: 12px; }
.empty { height: 100%; display: flex; align-items: center; justify-content: center; gap: 8px; color: var(--muted); padding: 20px; text-align: center; }
.empty svg { width: 16px; height: 16px; }
.cmp { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.cmp th { text-align: start; color: var(--muted); font-weight: 600; font-size: 11.5px; padding: 4px 8px; }
.cmp td { padding: 6px 8px; border-top: 1px solid var(--border); vertical-align: top; }
.cmp tr.on .new { color: var(--primary); font-weight: 600; }
.cur { color: var(--muted); }
.covers { margin-top: 14px; }
.crow { display: flex; gap: 14px; align-items: flex-start; }
.cthumb { width: 140px; height: 140px; border-radius: 10px; overflow: hidden; background: var(--surface-3); flex: none; }
.cthumb img { width: 100%; height: 100%; object-fit: cover; }
.cacts { display: flex; flex-direction: column; gap: 8px; align-items: flex-start; }
.cinfo { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--success); }
.cinfo svg { width: 14px; height: 14px; }
</style>
