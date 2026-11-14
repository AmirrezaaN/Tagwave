<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { Music, Play, Save, RotateCcw, FolderSearch, Trash2, ArrowUpDown, AudioLines } from '@lucide/vue'
import { state, visibleFiles, select, moveSelection, isDirty, revert, selectAll } from '../lib/store.js'
import { thumbUrl } from '../lib/api.js'
import { t } from '../lib/i18n.js'
import { duration } from '../lib/format.js'
import { playFile } from '../lib/player.js'
import { call } from '../lib/api.js'

const props = defineProps({ onRemove: Function, onSave: Function })
const ROW = 60
const scroller = ref(null)
const scrollTop = ref(0)
const viewH = ref(600)
const menu = ref(null)

const total = computed(() => visibleFiles.value.length)
const range = computed(() => {
  const start = Math.max(0, Math.floor(scrollTop.value / ROW) - 6)
  const end = Math.min(total.value, Math.ceil((scrollTop.value + viewH.value) / ROW) + 6)
  return { start, end }
})
const rows = computed(() => visibleFiles.value.slice(range.value.start, range.value.end)
  .map((f, i) => ({ f, top: (range.value.start + i) * ROW })))
const selSet = computed(() => new Set(state.selection))

function onScroll() { scrollTop.value = scroller.value.scrollTop }
let ro
onMounted(() => {
  ro = new ResizeObserver(() => { viewH.value = scroller.value?.clientHeight || 600 })
  ro.observe(scroller.value)
  window.addEventListener('click', closeMenu)
})
onBeforeUnmount(() => { ro?.disconnect(); window.removeEventListener('click', closeMenu) })

function display(f) {
  const d = state.drafts[f.id]?.fields || f.fields
  return {
    title: d.title || f.name.replace(/\.[^.]+$/, ''),
    sub: [d.artist || t('list.unknownArtist'), d.album].filter(Boolean).join(' · '),
    cover: (state.drafts[f.id]?.pictures || f.pictures)[0]?.blob,
  }
}

function onClick(e, f) {
  if (e.button !== 0 && selSet.value.has(f.id)) return
  select(f.id, { ctrl: e.ctrlKey || e.metaKey, shift: e.shiftKey })
  scroller.value?.focus()
}

function scrollIntoView(id) {
  const i = visibleFiles.value.findIndex((f) => f.id === id)
  if (i < 0 || !scroller.value) return
  const top = i * ROW
  const el = scroller.value
  if (top < el.scrollTop) el.scrollTop = top
  else if (top + ROW > el.scrollTop + el.clientHeight) el.scrollTop = top + ROW - el.clientHeight
}

function onKey(e) {
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault()
    const id = moveSelection(e.key === 'ArrowDown' ? 1 : -1, e.shiftKey)
    nextTick(() => scrollIntoView(id))
  } else if (e.key === 'Enter' && state.selection.length) {
    playFile(state.selection[state.selection.length - 1])
  } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') {
    e.preventDefault()
    selectAll()
  }
}

watch(() => state.selection.join(','), () => {
  const last = state.selection[state.selection.length - 1]
  if (last) nextTick(() => scrollIntoView(last))
})

// ------------------------------------------------------------ context menu
function openMenu(e, f) {
  e.preventDefault()
  if (!selSet.value.has(f.id)) select(f.id)
  const w = 230
  const h = 230
  menu.value = {
    x: Math.min(e.clientX, window.innerWidth - w - 8),
    y: Math.min(e.clientY, window.innerHeight - h - 8),
    file: f,
  }
}
function closeMenu() { menu.value = null }
function act(fn) { closeMenu(); fn() }
const anyDirty = computed(() => state.selection.some((id) => isDirty(id)))
</script>

<template>
  <aside class="list">
    <div class="list-head">
      <span class="count">
        {{ t('list.files', { n: state.files.length }) }}
        <template v-if="state.selection.length > 1"> · <b>{{ t('list.selected', { n: state.selection.length }) }}</b></template>
      </span>
      <label class="sort" :title="t('list.sort')">
        <ArrowUpDown />
        <select v-model="state.sort">
          <option value="added">{{ t('list.sortAdded') }}</option>
          <option value="name">{{ t('list.sortName') }}</option>
          <option value="title">{{ t('list.sortTitle') }}</option>
          <option value="artist">{{ t('list.sortArtist') }}</option>
          <option value="album">{{ t('list.sortAlbum') }}</option>
        </select>
      </label>
    </div>

    <div ref="scroller" class="scroller" tabindex="0" @scroll="onScroll" @keydown="onKey">
      <div class="spacer" :style="{ height: total * ROW + 'px' }">
        <div
          v-for="{ f, top } in rows" :key="f.id" class="row"
          :class="{ sel: selSet.has(f.id), playing: state.player.id === f.id }"
          :style="{ transform: `translateY(${top}px)` }"
          @mousedown.prevent="onClick($event, f)" @dblclick="playFile(f.id)" @contextmenu="openMenu($event, f)"
        >
          <div class="thumb">
            <img v-if="display(f).cover" :src="thumbUrl(display(f).cover, 96)" alt="" loading="lazy" draggable="false" />
            <Music v-else />
            <span v-if="state.player.id === f.id && state.player.playing" class="eq"><AudioLines /></span>
          </div>
          <div class="text">
            <div class="title ellipsis bidi">{{ display(f).title }}</div>
            <div class="sub ellipsis bidi">{{ display(f).sub }}</div>
          </div>
          <div class="meta">
            <span class="badge" :class="f.info.lossless ? 'lossless' : 'lossy'">{{ f.ext.toUpperCase() }}</span>
            <span class="dur ltr">{{ duration(f.info.duration) }}</span>
          </div>
          <span v-if="isDirty(f.id)" class="dirty" :title="t('list.modified')" />
        </div>
      </div>
      <div v-if="!total" class="nomatch">{{ t('list.noMatch') }}</div>
    </div>

    <Teleport to="body">
      <div v-if="menu" class="ctx" :style="{ left: menu.x + 'px', top: menu.y + 'px' }" @click.stop @contextmenu.prevent>
        <button @click="act(() => playFile(menu.file.id))"><Play /> {{ t('a.play') }}</button>
        <button :disabled="!anyDirty" @click="act(() => props.onSave(state.selection))"><Save /> {{ t('a.save') }}</button>
        <button :disabled="!anyDirty" @click="act(() => revert(state.selection))"><RotateCcw /> {{ t('a.revert') }}</button>
        <button @click="act(() => call('system.reveal', { path: menu.file.path }))"><FolderSearch /> {{ t('a.reveal') }}</button>
        <hr />
        <button class="danger" @click="act(() => props.onRemove())"><Trash2 /> {{ t('a.remove') }}</button>
      </div>
    </Teleport>
  </aside>
</template>

<style scoped>
.list { display: flex; flex-direction: column; min-height: 0; border-inline-end: 1px solid var(--border); background: color-mix(in srgb, var(--bg-2) 70%, transparent); }
.list-head { display: flex; align-items: center; justify-content: space-between; padding: 10px 14px 8px; font-size: 12px; color: var(--muted); }
.list-head b { color: var(--primary); font-weight: 600; }
.sort { display: flex; align-items: center; gap: 4px; color: var(--muted); }
.sort svg { width: 13px; height: 13px; }
.sort select { border: 0; background: transparent; color: var(--text-2); font-size: 12px; cursor: pointer; outline: none; }
.sort select option { background: var(--surface); }
.scroller { flex: 1; overflow-y: auto; overflow-x: hidden; outline: none; padding: 0 8px 12px; position: relative; }
.spacer { position: relative; }
.row {
  position: absolute; inset-inline: 0; height: 56px; margin: 2px 0; display: flex; align-items: center; gap: 11px;
  padding: 0 10px; border-radius: 10px; cursor: default; transition: background .12s;
}
.row:hover { background: var(--hover); }
.row.sel { background: var(--active); }
.row.sel::before { content: ''; position: absolute; inset-inline-start: 0; top: 12px; bottom: 12px; width: 3px; border-radius: 3px; background: var(--primary); }
.thumb {
  width: 40px; height: 40px; border-radius: 7px; overflow: hidden; flex: none; position: relative;
  background: var(--surface-3); display: grid; place-items: center; color: var(--faint);
  box-shadow: 0 2px 6px rgba(0, 0, 0, .25);
}
.thumb img { width: 100%; height: 100%; object-fit: cover; }
.thumb > svg { width: 18px; height: 18px; }
.eq { position: absolute; inset: 0; display: grid; place-items: center; background: rgba(10, 10, 20, .55); color: #fff; }
.eq svg { width: 18px; height: 18px; animation: pulse 1.1s ease-in-out infinite; }
@keyframes pulse { 50% { opacity: .45; } }
.text { flex: 1; min-width: 0; }
.title { font-weight: 560; font-size: 13.5px; }
.row.playing .title { color: var(--primary); }
.sub { font-size: 12px; color: var(--muted); margin-top: 1px; }
.meta { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; }
.dur { font-size: 11px; color: var(--faint); font-variant-numeric: tabular-nums; }
.badge { height: 18px; font-size: 10px; padding: 0 6px; }
.dirty { position: absolute; top: 9px; inset-inline-start: 6px; width: 7px; height: 7px; border-radius: 50%; background: var(--warning); box-shadow: 0 0 0 2px var(--bg-2); }
.nomatch { padding: 30px 16px; text-align: center; color: var(--muted); }
.ctx {
  position: fixed; z-index: 100; min-width: 220px; padding: 5px; border-radius: 10px;
  background: var(--surface); border: 1px solid var(--border-strong); box-shadow: var(--shadow-lg);
  animation: pop-in .12s var(--ease);
}
.ctx button {
  display: flex; align-items: center; gap: 10px; width: 100%; height: 32px; padding: 0 10px; border: 0;
  background: transparent; border-radius: 6px; text-align: start; font-size: 13px;
}
.ctx button:hover:not(:disabled) { background: var(--hover); }
.ctx button:disabled { opacity: .4; cursor: default; }
.ctx button svg { width: 15px; height: 15px; color: var(--muted); }
.ctx button.danger, .ctx button.danger svg { color: var(--danger); }
.ctx hr { border: 0; border-top: 1px solid var(--border); margin: 4px 2px; }
</style>
