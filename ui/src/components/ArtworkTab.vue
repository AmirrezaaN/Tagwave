<script setup>
import { computed, ref } from 'vue'
import { ImagePlus, Crop, Download, Trash2, Replace, Star, Globe, ShieldCheck, Layers } from '@lucide/vue'
import { state, commonPictures, setPictures, setFrontCover, fileMap, openDialog, toast } from '../lib/store.js'
import { call, blobUrl } from '../lib/api.js'
import { t, errorText } from '../lib/i18n.js'
import { size, dims } from '../lib/format.js'
import { pickImage, imageFromFile } from '../lib/actions.js'

const props = defineProps({ ids: Array })
const pics = computed(() => (props.ids.length ? commonPictures(props.ids) : null))
const mixed = computed(() => props.ids.length > 1 && pics.value === null)
const supportsTypes = computed(() => props.ids.every((id) => fileMap.value.get(id)?.pictureTypes))
const supportsDesc = computed(() => props.ids.every((id) => fileMap.value.get(id)?.pictureDesc))
const dropOn = ref(false)
const TYPES = Array.from({ length: 21 }, (_, i) => i)

function update(fn) {
  const list = JSON.parse(JSON.stringify(pics.value || []))
  fn(list)
  setPictures(props.ids, list)
}
function note(img) {
  if (img?.converted) toast(t('art.converted'), 'info')
}
async function add() {
  const img = await pickImage()
  if (!img) return
  note(img)
  if (mixed.value || !pics.value?.length) setFrontCover(props.ids, img)
  else update((l) => l.push({ ...img, type: l.some((p) => p.type === 3) ? 0 : 3, desc: '' }))
}
async function replace(i) {
  const img = await pickImage()
  if (!img) return
  note(img)
  update((l) => { l[i] = { ...img, type: l[i].type, desc: l[i].desc } })
}
function remove(i) { update((l) => l.splice(i, 1)) }
function makeFront(i) {
  update((l) => {
    const p = l.splice(i, 1)[0]
    l.forEach((x) => { if (x.type === 3) x.type = 0 })
    p.type = 3
    l.unshift(p)
  })
}
function setType(i, v) { update((l) => { l[i].type = +v }) }
function setDesc(i, v) { update((l) => { l[i].desc = v }) }
function crop(i) {
  openDialog('crop', {
    pic: pics.value[i],
    onDone: (img) => update((l) => { l[i] = { ...img, type: l[i].type, desc: l[i].desc } }),
  })
}
async function exportImg(p) {
  try { await call('images.export', { blob: p.blob, name: 'cover' }) } catch (e) { toast(errorText(e), 'error') }
}
async function onDrop(e) {
  dropOn.value = false
  const file = [...(e.dataTransfer?.files || [])].find((f) => f.type.startsWith('image/'))
  if (!file) return
  e.stopPropagation()
  const img = await imageFromFile(file)
  if (!img) return
  note(img)
  if (mixed.value || !pics.value?.length) setFrontCover(props.ids, img)
  else update((l) => l.push({ ...img, type: l.some((p) => p.type === 3) ? 0 : 3, desc: '' }))
}
function onDragOver(e) {
  if ([...(e.dataTransfer?.items || [])].some((i) => i.kind === 'file')) { e.preventDefault(); dropOn.value = true }
}
function removeAll() { setPictures(props.ids, []) }
</script>

<template>
  <div class="art" v-if="ids.length">
    <div class="note" v-if="ids.length > 1"><Layers /> {{ t('art.batch', { n: ids.length }) }}</div>
    <div class="note" v-if="!supportsTypes"><Star /> {{ t('art.noTypes') }}</div>

    <div v-if="mixed" class="mixed card">
      <p>{{ t('art.different') }}</p>
      <div class="row">
        <button class="btn" @click="add"><Replace /> {{ t('art.replace') }}</button>
        <button class="btn ghost danger" @click="removeAll"><Trash2 /> {{ t('art.delete') }}</button>
      </div>
    </div>

    <div class="grid">
      <div v-for="(p, i) in (pics || [])" :key="p.blob + i" class="pic card">
        <div class="img checker">
          <img :src="blobUrl(p.blob)" alt="" draggable="false" />
          <span v-if="p.type === 3 || (!supportsTypes && i === 0)" class="front"><Star /> {{ t('art.front') }}</span>
        </div>
        <div class="meta">
          <div class="spec ltr">
            <b>{{ p.mime === 'image/png' ? 'PNG' : p.mime === 'image/jpeg' ? 'JPEG' : p.mime }}</b>
            <span>{{ dims(p.width, p.height) }}</span>
            <span>{{ size(p.size) }}</span>
          </div>
          <div class="fields" v-if="supportsTypes || supportsDesc">
            <select v-if="supportsTypes" class="select" :value="p.type" @change="setType(i, $event.target.value)" :aria-label="t('art.type')">
              <option v-for="n in TYPES" :key="n" :value="n">{{ t('pt.' + n) }}</option>
            </select>
            <input v-if="supportsDesc" class="input" :value="p.desc" :placeholder="t('art.desc')" dir="auto"
                   @input="setDesc(i, $event.target.value)" />
          </div>
          <div class="acts">
            <button class="btn sm" @click="crop(i)"><Crop /> {{ t('art.crop') }}</button>
            <button class="btn sm ghost" @click="replace(i)" :title="t('art.replace')"><Replace /></button>
            <button class="btn sm ghost" @click="exportImg(p)" :title="t('art.export')"><Download /></button>
            <button v-if="i > 0" class="btn sm ghost" @click="makeFront(i)" :title="t('art.front')"><Star /></button>
            <div class="grow" />
            <button class="btn sm ghost danger" @click="remove(i)" :title="t('art.delete')"><Trash2 /></button>
          </div>
        </div>
      </div>

      <div class="add" :class="{ on: dropOn }" @dragover="onDragOver" @dragleave="dropOn = false" @drop.prevent="onDrop">
        <ImagePlus />
        <p>{{ t('art.drop') }}</p>
        <div class="row">
          <button class="btn primary" @click="add">{{ t('art.choose') }}</button>
          <button class="btn ghost" v-if="ids.length === 1" @click="openDialog('lookup')"><Globe /> {{ t('art.online') }}</button>
        </div>
      </div>
    </div>

    <p class="guarantee"><ShieldCheck /> {{ t('art.original') }}</p>
  </div>
</template>

<style scoped>
.note { display: flex; align-items: center; gap: 8px; font-size: 12.5px; color: var(--text-2); margin-bottom: 12px; padding: 9px 12px; border-radius: 10px; background: var(--primary-soft); }
.note svg { width: 15px; height: 15px; color: var(--primary); flex: none; }
.mixed { padding: 16px; margin-bottom: 16px; }
.mixed p { margin: 0 0 12px; color: var(--text-2); }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }
.pic { overflow: hidden; display: flex; flex-direction: column; }
.img { aspect-ratio: 1; position: relative; display: grid; place-items: center; overflow: hidden; }
.img img { max-width: 100%; max-height: 100%; object-fit: contain; }
.front { position: absolute; top: 10px; inset-inline-start: 10px; display: flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 650; padding: 3px 8px; border-radius: 20px; background: rgba(10, 10, 18, .7); color: #fff; backdrop-filter: blur(6px); }
.front svg { width: 12px; height: 12px; fill: #fbbf24; color: #fbbf24; }
.meta { padding: 12px; display: flex; flex-direction: column; gap: 10px; }
.spec { display: flex; gap: 10px; font-size: 12px; color: var(--muted); }
.spec b { color: var(--text-2); }
.fields { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.fields .select, .fields .input { height: 32px; font-size: 12.5px; }
.fields > :only-child { grid-column: span 2; }
.acts { display: flex; gap: 4px; align-items: center; }
.add {
  min-height: 260px; border: 1.5px dashed var(--border-strong); border-radius: var(--radius); display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 10px; padding: 20px; text-align: center; color: var(--muted); transition: .15s;
}
.add.on { border-color: var(--primary); background: var(--primary-soft); color: var(--text); }
.add > svg { width: 34px; height: 34px; color: var(--faint); }
.add p { margin: 0; font-size: 12.5px; max-width: 220px; line-height: 1.6; }
.guarantee { display: flex; align-items: center; gap: 6px; margin-top: 18px; font-size: 12px; color: var(--muted); }
.guarantee svg { width: 14px; height: 14px; color: var(--success); }
</style>
