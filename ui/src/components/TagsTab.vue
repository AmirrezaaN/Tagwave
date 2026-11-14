<script setup>
import { computed } from 'vue'
import { ListOrdered, Plus, Trash2 } from '@lucide/vue'
import { state, commonField, setField, visibleFiles, MIXED } from '../lib/store.js'
import { t } from '../lib/i18n.js'
import FieldInput from './FieldInput.vue'

const props = defineProps({ ids: Array })
const GENRES = ['Pop', 'Rock', 'Hip-Hop', 'Rap', 'R&B', 'Electronic', 'Dance', 'House', 'Techno', 'Ambient', 'Jazz', 'Blues',
  'Classical', 'Soundtrack', 'Country', 'Folk', 'Metal', 'Alternative', 'Indie', 'Reggae', 'Latin', 'World', 'Soul', 'Funk',
  'Lo-Fi', 'Instrumental', 'Persian Pop', 'Persian Traditional', 'پاپ', 'سنتی', 'راک', 'رپ', 'تلفیقی', 'بی‌کلام']

function suggestions(key) {
  const set = new Set()
  for (const f of state.files) {
    const v = state.drafts[f.id]?.fields[key]
    if (v) set.add(v)
    if (set.size > 300) break
  }
  if (key === 'genre') GENRES.forEach((g) => set.add(g))
  return [...set].sort((a, b) => a.localeCompare(b))
}
const lists = computed(() => ({
  artist: suggestions('artist'), album: suggestions('album'), albumartist: suggestions('albumartist'),
  genre: suggestions('genre'), composer: suggestions('composer'), publisher: suggestions('publisher'),
}))

const compilation = computed(() => commonField(props.ids, 'compilation'))
function setCompilation(on) { setField(props.ids, 'compilation', on ? '1' : '') }

function autoNumber() {
  const order = visibleFiles.value.map((f) => f.id).filter((id) => props.ids.includes(id))
  order.forEach((id, i) => {
    state.drafts[id].fields.track = String(i + 1)
    state.drafts[id].fields.tracktotal = String(order.length)
  })
}

// ------------------------------------------------------------ custom fields
const single = computed(() => (props.ids.length === 1 ? props.ids[0] : null))
const custom = computed(() => (single.value ? state.drafts[single.value]?.custom || [] : []))
function addCustom() { state.drafts[single.value].custom.push(['', '']) }
function removeCustom(i) { state.drafts[single.value].custom.splice(i, 1) }
function setCustom(i, j, v) { state.drafts[single.value].custom[i][j] = v }
</script>

<template>
  <div class="tags" v-if="ids.length">
    <datalist v-for="(vals, key) in lists" :key="key" :id="'dl-' + key">
      <option v-for="v in vals" :key="v" :value="v" />
    </datalist>

    <section class="sec">
      <h3>{{ t('ed.sec.main') }}</h3>
      <div class="grid">
        <FieldInput class="c12" :ids="ids" field="title" :label="t('f.title')" />
        <FieldInput class="c6" :ids="ids" field="artist" :label="t('f.artist')" list="dl-artist" />
        <FieldInput class="c6" :ids="ids" field="albumartist" :label="t('f.albumartist')" list="dl-albumartist" />
        <FieldInput class="c6" :ids="ids" field="album" :label="t('f.album')" list="dl-album" />
        <FieldInput class="c3" :ids="ids" field="genre" :label="t('f.genre')" list="dl-genre" />
        <FieldInput class="c3" :ids="ids" field="date" :label="t('f.date')" kind="date" />
      </div>
    </section>

    <section class="sec">
      <div class="sec-head">
        <h3>{{ t('ed.sec.numbers') }}</h3>
        <button v-if="ids.length > 1" class="btn sm ghost" @click="autoNumber" :title="t('ed.autoNumberHint', { n: ids.length })">
          <ListOrdered /> {{ t('ed.autoNumber') }}
        </button>
      </div>
      <div class="grid">
        <div class="c3 pair">
          <FieldInput :ids="ids" field="track" :label="t('f.track')" kind="number" />
          <span class="of">/</span>
          <FieldInput :ids="ids" field="tracktotal" :label="t('f.tracktotal')" kind="number" />
        </div>
        <div class="c3 pair">
          <FieldInput :ids="ids" field="disc" :label="t('f.disc')" kind="number" />
          <span class="of">/</span>
          <FieldInput :ids="ids" field="disctotal" :label="t('f.disctotal')" kind="number" />
        </div>
        <FieldInput class="c2" :ids="ids" field="bpm" :label="t('f.bpm')" kind="decimal" />
        <div class="c4 switch-field">
          <label class="label">&nbsp;</label>
          <label class="check-row">
            <span class="switch"><input type="checkbox" :checked="compilation === '1'" :indeterminate.prop="compilation === MIXED"
                                       @change="setCompilation($event.target.checked)" /><span /></span>
            <span>{{ t('f.compilation') }}</span>
            <span v-if="compilation === MIXED" class="muted">· {{ t('ed.mixed') }}</span>
          </label>
        </div>
      </div>
    </section>

    <section class="sec">
      <h3>{{ t('ed.sec.people') }}</h3>
      <div class="grid">
        <FieldInput class="c6" :ids="ids" field="composer" :label="t('f.composer')" list="dl-composer" />
        <FieldInput class="c6" :ids="ids" field="lyricist" :label="t('f.lyricist')" />
        <FieldInput class="c6" :ids="ids" field="conductor" :label="t('f.conductor')" />
        <FieldInput class="c6" :ids="ids" field="publisher" :label="t('f.publisher')" list="dl-publisher" />
      </div>
    </section>

    <section class="sec">
      <h3>{{ t('ed.sec.more') }}</h3>
      <div class="grid">
        <FieldInput class="c12" :ids="ids" field="comment" :label="t('f.comment')" kind="textarea" :rows="2" />
        <FieldInput class="c6" :ids="ids" field="copyright" :label="t('f.copyright')" />
        <FieldInput class="c6" :ids="ids" field="encodedby" :label="t('f.encodedby')" />
        <FieldInput class="c4" :ids="ids" field="isrc" :label="t('f.isrc')" />
        <FieldInput class="c8" :ids="ids" field="grouping" :label="t('f.grouping')" />
      </div>
    </section>

    <section class="sec">
      <div class="sec-head">
        <h3>{{ t('ed.sec.custom') }}</h3>
        <button v-if="single" class="btn sm ghost" @click="addCustom"><Plus /> {{ t('ed.customAdd') }}</button>
      </div>
      <p v-if="!single" class="muted small">{{ t('ed.customSingle') }}</p>
      <template v-else>
        <p v-if="!custom.length" class="muted small">{{ t('ed.customEmpty') }}</p>
        <div v-for="(c, i) in custom" :key="i" class="custom-row">
          <input class="input key" :value="c[0]" :placeholder="t('ed.customKey')" dir="ltr" spellcheck="false"
                 @input="setCustom(i, 0, $event.target.value)" />
          <input class="input" :value="c[1]" :placeholder="t('ed.customValue')" dir="auto" spellcheck="false"
                 @input="setCustom(i, 1, $event.target.value)" />
          <button class="btn ghost icon sm danger" @click="removeCustom(i)" :aria-label="t('a.delete')"><Trash2 /></button>
        </div>
      </template>
    </section>
  </div>
</template>

<style scoped>
.tags { max-width: 980px; }
.sec { margin-bottom: 26px; }
.sec-head { display: flex; align-items: center; justify-content: space-between; }
h3 { margin: 0 0 12px; font-size: 11.5px; text-transform: uppercase; letter-spacing: .08em; color: var(--faint); font-weight: 700; }
:root[lang='fa'] h3 { letter-spacing: 0; text-transform: none; font-size: 12.5px; }
.sec-head h3 { margin-bottom: 12px; }
.sec-head .btn { margin-top: -10px; }
.grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 14px 14px; }
.c12 { grid-column: span 12; } .c8 { grid-column: span 8; } .c6 { grid-column: span 6; } .c4 { grid-column: span 4; }
.c3 { grid-column: span 3; } .c2 { grid-column: span 2; }
@media (max-width: 1250px) { .c3 { grid-column: span 6; } .c2 { grid-column: span 4; } .c4.switch-field { grid-column: span 8; } }
.pair { display: grid; grid-template-columns: 1fr auto 1fr; align-items: end; gap: 6px; }
.of { color: var(--faint); padding-bottom: 9px; }
.check-row { display: flex; align-items: center; gap: 10px; height: 36px; cursor: pointer; }
.custom-row { display: grid; grid-template-columns: 220px 1fr auto; gap: 8px; margin-bottom: 8px; }
.custom-row .key { font-family: var(--mono); font-size: 12.5px; }
.small { font-size: 12.5px; margin: 0; }
</style>
