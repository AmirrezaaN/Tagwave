<script setup>
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { Music, Play, Pause, Save, RotateCcw, FolderSearch, Layers, ImagePlus, TriangleAlert } from '@lucide/vue'
import {
  state, selectedFiles, editableSelection, isDirty, revert, commonField, commonPictures, setFrontCover, MIXED, toast,
} from '../lib/store.js'
import { call, thumbUrl } from '../lib/api.js'
import { t } from '../lib/i18n.js'
import { qualityLine } from '../lib/format.js'
import { playFile, toggle } from '../lib/player.js'
import { imageFromClipboardEvent, imageFromFile } from '../lib/actions.js'
import TagsTab from './TagsTab.vue'
import ArtworkTab from './ArtworkTab.vue'
import LyricsTab from './LyricsTab.vue'
import QualityTab from './QualityTab.vue'
import DetailsTab from './DetailsTab.vue'

const props = defineProps({ onSave: Function })
const files = selectedFiles
const ids = computed(() => state.selection)
const single = computed(() => (files.value.length === 1 ? files.value[0] : null))
const editIds = editableSelection
const tabs = computed(() => [
  { id: 'tags', label: t('ed.tabs.tags') },
  { id: 'artwork', label: t('ed.tabs.artwork') },
  { id: 'lyrics', label: t('ed.tabs.lyrics') },
  { id: 'quality', label: t('ed.tabs.quality') },
  { id: 'details', label: t('ed.tabs.details') },
])

const pics = computed(() => (editIds.value.length ? commonPictures(editIds.value) : single.value?.pictures || []))
const cover = computed(() => {
  if (pics.value && pics.value.length) return pics.value.find((p) => p.type === 3)?.blob || pics.value[0].blob
  return null
})
const stack = computed(() => {
  const out = []
  for (const f of files.value) {
    const b = (state.drafts[f.id]?.pictures || f.pictures)[0]?.blob
    if (b && !out.includes(b)) out.push(b)
    if (out.length >= 3) break
  }
  return out
})
const title = computed(() => {
  if (single.value) return state.drafts[single.value.id]?.fields.title || single.value.name.replace(/\.[^.]+$/, '')
  return t('ed.multi', { n: files.value.length })
})
const subtitle = computed(() => {
  const keys = ['artist', 'album', 'date']
  const ids_ = files.value.map((f) => f.id)
  return keys.map((k) => commonField(ids_, k)).filter((v) => v && v !== MIXED).map((v, i) => (i === 2 ? String(v).slice(0, 4) : v)).join(' · ')
})
const dirty = computed(() => ids.value.some((id) => isDirty(id)))
const isPlayingThis = computed(() => single.value && state.player.id === single.value.id && state.player.playing)
const formats = computed(() => [...new Set(files.value.map((f) => f.info.codec))])
const allLossless = computed(() => files.value.every((f) => f.info.lossless))
const anyLossless = computed(() => files.value.some((f) => f.info.lossless))

function playPause() {
  if (!single.value) return
  if (state.player.id === single.value.id) toggle()
  else playFile(single.value.id)
}

// ----------------------------------------------------- drop / paste a cover
const dropActive = ref(false)
async function onDrop(e) {
  dropActive.value = false
  const file = [...(e.dataTransfer?.files || [])].find((f) => f.type.startsWith('image/'))
  if (!file || !editIds.value.length) return
  e.stopPropagation()
  const img = await imageFromFile(file)
  if (img) { setFrontCover(editIds.value, img); toast(t('t.coverSet'), 'success') }
}
function onDragOver(e) {
  if ([...(e.dataTransfer?.items || [])].some((i) => i.kind === 'file' && i.type.startsWith('image/'))) {
    e.preventDefault()
    dropActive.value = true
  }
}
async function onPaste(e) {
  const el = e.target
  if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') || state.dialog || !editIds.value.length) return
  const img = await imageFromClipboardEvent(e)
  if (img) { setFrontCover(editIds.value, img); toast(t('t.coverSet'), 'success') }
}
onMounted(() => window.addEventListener('paste', onPaste))
onBeforeUnmount(() => window.removeEventListener('paste', onPaste))
</script>

<template>
  <section class="editor" v-if="files.length">
    <div class="hero">
      <div class="ambient" v-if="cover" :style="{ backgroundImage: `url(${thumbUrl(cover, 256)})` }" />
      <div class="hero-in">
        <div class="cover" :class="{ drop: dropActive, stack: !single && stack.length > 1 }"
             @dragover="onDragOver" @dragleave="dropActive = false" @drop.prevent="onDrop"
             @click="state.tab = 'artwork'" :title="t('art.title')">
          <template v-if="single || pics">
            <img v-if="cover" :src="thumbUrl(cover, 512)" alt="" draggable="false" />
            <div v-else class="noart"><Music /></div>
          </template>
          <template v-else>
            <img v-for="(b, i) in stack" :key="b" :src="thumbUrl(b, 256)" class="layer" :style="{ '--i': i }" alt="" draggable="false" />
            <div v-if="!stack.length" class="noart"><Layers /></div>
          </template>
          <div class="cover-hint"><ImagePlus /></div>
        </div>
        <div class="info">
          <div class="kicker" v-if="!single"><Layers /> {{ t('ed.multi', { n: files.length }) }}</div>
          <h1 class="ellipsis bidi" :title="title">{{ title }}</h1>
          <div class="subtitle ellipsis bidi">{{ subtitle || ' ' }}</div>
          <div class="badges">
            <span class="badge ltr" v-for="c in formats.slice(0, 4)" :key="c">{{ c }}</span>
            <span class="badge ltr" v-if="single">{{ qualityLine(single.info) }}</span>
            <span class="badge" :class="allLossless ? 'lossless' : anyLossless ? 'info' : 'lossy'">
              {{ allLossless ? t('d.lossless') : anyLossless ? t('d.lossless') + ' + ' + t('d.lossy') : t('d.lossy') }}
            </span>
            <span class="badge ltr" v-if="single && single.tagFormat">{{ single.tagFormat }}</span>
          </div>
          <div class="actions">
            <button class="btn" v-if="single" @click="playPause"><Pause v-if="isPlayingThis" /><Play v-else /> {{ isPlayingThis ? t('a.pause') : t('a.play') }}</button>
            <button class="btn primary" :disabled="!dirty || state.saving" @click="props.onSave(ids)"><Save /> {{ t('a.save') }}</button>
            <button class="btn ghost" :disabled="!dirty" @click="revert(ids)"><RotateCcw /> {{ t('a.revert') }}</button>
            <button class="btn ghost" v-if="single" @click="call('system.reveal', { path: single.path })"><FolderSearch /> {{ t('a.reveal') }}</button>
          </div>
        </div>
      </div>
      <nav class="tabs" role="tablist">
        <button v-for="tb in tabs" :key="tb.id" role="tab" :aria-selected="state.tab === tb.id"
                :class="{ on: state.tab === tb.id }" @click="state.tab = tb.id">{{ tb.label }}</button>
      </nav>
    </div>

    <div class="cant" v-if="!editIds.length || editIds.length < files.length">
      <TriangleAlert /> {{ t('ed.cantTag') }}
    </div>

    <div class="tab-body">
      <TagsTab v-if="state.tab === 'tags'" :ids="editIds" />
      <ArtworkTab v-else-if="state.tab === 'artwork'" :ids="editIds" />
      <LyricsTab v-else-if="state.tab === 'lyrics'" :ids="editIds" />
      <QualityTab v-else-if="state.tab === 'quality'" :file="single" />
      <DetailsTab v-else :files="files" />
    </div>
  </section>

  <section class="editor none" v-else>
    <div class="none-in">
      <Music />
      <h2>{{ t('ed.none') }}</h2>
      <p>{{ t('ed.noneSub') }}</p>
    </div>
  </section>
</template>

<style scoped>
.editor { min-width: 0; min-height: 0; display: flex; flex-direction: column; position: relative; overflow: hidden; }
.hero { position: relative; padding: 26px 30px 0; flex: none; }
.ambient {
  position: absolute; inset: -60px -40px 0; background-size: cover; background-position: center;
  filter: blur(60px) saturate(1.5); opacity: .32; pointer-events: none;
  mask-image: linear-gradient(to bottom, #000 30%, transparent);
}
:root[data-theme='light'] .ambient { opacity: .22; }
.hero-in { position: relative; display: flex; gap: 26px; align-items: flex-end; }
.cover {
  width: 176px; height: 176px; flex: none; border-radius: 14px; overflow: hidden; position: relative; cursor: pointer;
  background: var(--surface-3); box-shadow: 0 18px 40px -12px rgba(0, 0, 0, .6), 0 0 0 1px var(--border);
  transition: transform .2s var(--ease), box-shadow .2s;
}
.cover:hover { transform: translateY(-2px); }
.cover img { width: 100%; height: 100%; object-fit: cover; }
.cover.stack { overflow: visible; background: transparent; box-shadow: none; }
.cover .layer {
  position: absolute; inset: 0; border-radius: 12px; box-shadow: 0 12px 30px -10px rgba(0,0,0,.6);
  transform: translate(calc(var(--i) * 14px), calc(var(--i) * -10px)) scale(calc(1 - var(--i) * .08));
  z-index: calc(10 - var(--i)); outline: 1px solid var(--border);
}
.noart { width: 100%; height: 100%; display: grid; place-items: center; color: var(--faint); background: linear-gradient(135deg, var(--surface-3), var(--surface-2)); }
.noart svg { width: 54px; height: 54px; }
.cover-hint { position: absolute; inset: 0; display: grid; place-items: center; background: rgba(8, 8, 14, .45); color: #fff; opacity: 0; transition: opacity .15s; z-index: 20; border-radius: inherit; }
.cover-hint svg { width: 30px; height: 30px; }
.cover:hover .cover-hint, .cover.drop .cover-hint { opacity: 1; }
.cover.drop { outline: 3px solid var(--primary); outline-offset: 3px; }
.info { min-width: 0; flex: 1; padding-bottom: 4px; }
.kicker { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--primary); font-weight: 600; margin-bottom: 4px; }
.kicker svg { width: 14px; height: 14px; }
h1 { margin: 0; font-size: 30px; line-height: 1.2; font-weight: 750; letter-spacing: -.025em; }
.subtitle { margin-top: 4px; color: var(--text-2); font-size: 14.5px; }
.badges { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
.tabs { position: relative; display: flex; gap: 2px; margin-top: 22px; border-bottom: 1px solid var(--border); }
.tabs button {
  position: relative; height: 38px; padding: 0 14px; border: 0; background: transparent; color: var(--muted);
  font-weight: 600; font-size: 13px; border-radius: 8px 8px 0 0; transition: color .15s, background .15s;
}
.tabs button:hover { color: var(--text); background: var(--hover); }
.tabs button.on { color: var(--text); }
.tabs button.on::after { content: ''; position: absolute; inset-inline: 10px; bottom: -1px; height: 2px; border-radius: 2px; background: var(--grad); }
.cant { margin: 12px 30px 0; padding: 10px 12px; display: flex; gap: 8px; align-items: center; border-radius: 10px; background: var(--warning-soft); color: var(--warning); font-size: 12.5px; }
.cant svg { width: 16px; height: 16px; flex: none; }
.tab-body { flex: 1; min-height: 0; overflow: auto; padding: 20px 30px 40px; }
.none { display: grid; place-items: center; }
/* Compact header on short or narrow windows so the fields keep enough room. */
@media (max-height: 780px), (max-width: 1150px) {
  .hero { padding: 16px 22px 0; }
  .hero-in { gap: 18px; }
  .cover { width: 124px; height: 124px; border-radius: 11px; }
  h1 { font-size: 23px; }
  .subtitle { font-size: 13.5px; }
  .badges { margin-top: 8px; }
  .actions { margin-top: 10px; }
  .tabs { margin-top: 14px; }
  .tab-body { padding: 16px 22px 30px; }
  .cant { margin: 10px 22px 0; }
}
.none-in { text-align: center; color: var(--muted); }
.none-in svg { width: 46px; height: 46px; color: var(--faint); }
.none-in h2 { margin: 12px 0 4px; font-size: 17px; color: var(--text-2); }
.none-in p { margin: 0; font-size: 13px; }
</style>
