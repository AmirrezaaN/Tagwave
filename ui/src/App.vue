<script setup>
import { onMounted, onBeforeUnmount, watch, computed } from 'vue'
import { call, connectEvents, onEvent } from './lib/api.js'
import { t, applyLanguage, errorText } from './lib/i18n.js'
import {
  state, upsertFiles, dirtyIds, saveFiles, toast, confirmDialog, applyTheme, selectAll, editableSelection,
  openDialog, removeFiles, setFrontCover, selectedFiles,
} from './lib/store.js'
import TopBar from './components/TopBar.vue'
import FileList from './components/FileList.vue'
import Editor from './components/Editor.vue'
import EmptyState from './components/EmptyState.vue'
import PlayerBar from './components/PlayerBar.vue'
import Toasts from './components/Toasts.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import ExportDialog from './components/ExportDialog.vue'
import RenameDialog from './components/RenameDialog.vue'
import LookupDialog from './components/LookupDialog.vue'
import CropDialog from './components/CropDialog.vue'
import SettingsDialog from './components/SettingsDialog.vue'
import JobsBar from './components/JobsBar.vue'
import { addFiles, addFolder } from './lib/actions.js'

const dialogs = { export: ExportDialog, rename: RenameDialog, lookup: LookupDialog, crop: CropDialog, settings: SettingsDialog }
const dialogComp = computed(() => (state.dialog ? dialogs[state.dialog.name] : null))

async function boot() {
  await connectEvents()
  const info = await call('init')
  state.info = info
  state.settings = info.settings
  applyLanguage(state.settings.language)
  applyTheme()
  upsertFiles(info.files)
  state.ready = true
}

watch(() => state.settings.language, (l) => applyLanguage(l))
watch(() => state.settings.theme, () => applyTheme())

let mq
onMounted(() => {
  boot().catch((e) => toast(errorText(e), 'error'))
  mq = matchMedia('(prefers-color-scheme: light)')
  mq.addEventListener('change', applyTheme)
  window.addEventListener('keydown', onKey)
  window.addEventListener('dragover', prevent)
  window.addEventListener('drop', prevent)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  mq?.removeEventListener('change', applyTheme)
})

function prevent(e) { e.preventDefault() }

// --------------------------------------------------------------- backend events
onEvent(async (msg) => {
  const d = msg.data
  if (msg.type === 'job' && d.state !== 'running') {
    if (d.kind === 'load' && d.result) {
      if (d.result.added && d.meta?.origin !== 'convert') toast(t('t.added', { n: d.result.added }), 'success')
      if (d.result.errors?.length) toast(t('t.loadErrors', { n: d.result.errors.length }) + ' — ' + errorText(d.result.errors[0].error), 'error')
    }
  }
  if (msg.type === 'window.closeRequested') onCloseRequested()
  if (msg.type === 'drop.unsupported') toast(t('t.unsupportedDrop'), 'error')
  if (msg.type === 'images.dropped') {
    const ids = editableSelection.value
    if (!ids.length) return toast(t('t.imagesDropped'), 'info')
    try {
      const res = await call('images.fromPaths', { paths: d.paths.slice(0, 1) })
      if (res.images[0]) { setFrontCover(ids, res.images[0]); toast(t('t.coverSet'), 'success') }
      if (res.errors[0]) toast(errorText(res.errors[0].error), 'error')
    } catch (e) { toast(errorText(e), 'error') }
  }
})

async function onCloseRequested() {
  if (state.confirm) return
  const choice = await confirmDialog({
    title: t('cl.title'), body: t('cl.body', { n: dirtyIds.value.length }),
    buttons: [{ label: t('a.cancel'), value: 'cancel' }, { label: t('cl.discard'), value: 'discard', kind: 'danger' },
      { label: t('cl.save'), value: 'save', kind: 'primary' }],
  })
  if (choice === 'discard') return call('window.close')
  if (choice === 'save') {
    const res = await saveAll()
    if (!res?.errors?.length) call('window.close')
  }
}

async function saveAll() {
  return doSave(dirtyIds.value)
}

async function doSave(ids) {
  try {
    const res = await saveFiles(ids)
    if (res.saved?.length) toast(res.saved.length === 1 ? t('t.savedOne') : t('t.saved', { n: res.saved.length }), 'success')
    if (res.errors?.length) toast(t('t.saveErrors', { n: res.errors.length }) + ' — ' + errorText(res.errors[0].error), 'error')
    return res
  } catch (e) {
    toast(errorText(e), 'error')
    return { errors: [e] }
  }
}

// -------------------------------------------------------------- keyboard
function inField(e) {
  const el = e.target
  return el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable)
}

function onKey(e) {
  if (state.confirm) return
  const ctrl = e.ctrlKey || e.metaKey
  const k = e.key.toLowerCase()
  if (ctrl && k === 's') { e.preventDefault(); doSave(dirtyIds.value); return }
  if (state.dialog) return
  if (ctrl && k === 'o') { e.preventDefault(); e.shiftKey ? addFolder() : addFiles(); return }
  if (ctrl && k === 'e' && state.selection.length) { e.preventDefault(); openDialog('export'); return }
  if (e.key === 'F2' && state.selection.length) { e.preventDefault(); openDialog('rename'); return }
  if (ctrl && k === 'f') { e.preventDefault(); document.getElementById('tw-search')?.focus(); return }
  if (inField(e)) return
  if (ctrl && k === 'a') { e.preventDefault(); selectAll(); return }
  if (e.key === 'Delete' && selectedFiles.value.length) { e.preventDefault(); askRemove(); return }
}

async function askRemove() {
  const ids = [...state.selection]
  const dirty = ids.filter((id) => dirtyIds.value.includes(id))
  if (dirty.length) {
    const v = await confirmDialog({
      title: t('cl.title'), body: t('cl.body', { n: dirty.length }),
      buttons: [{ label: t('a.cancel'), value: false }, { label: t('a.remove'), value: true, kind: 'danger' }],
    })
    if (!v) return
  }
  removeFiles(ids)
}

</script>

<template>
  <div class="app" :class="{ ready: state.ready }">
    <TopBar :on-save="() => doSave(dirtyIds)" />
    <main class="main" v-if="state.ready">
      <template v-if="state.files.length">
        <FileList :on-remove="askRemove" :on-save="doSave" />
        <Editor :on-save="doSave" />
      </template>
      <EmptyState v-else />
    </main>
    <PlayerBar />
    <JobsBar />
    <Toasts />
    <component :is="dialogComp" v-if="dialogComp" v-bind="state.dialog.props" :key="state.dialog.name" />
    <ConfirmDialog />
  </div>
</template>

<style scoped>
.app {
  height: 100%;
  display: grid;
  grid-template-rows: var(--topbar-h) 1fr var(--player-h);
  background:
    radial-gradient(1200px 500px at 85% -10%, rgba(99, 102, 241, .07), transparent 60%),
    radial-gradient(900px 400px at -10% 110%, rgba(34, 211, 238, .05), transparent 60%),
    var(--bg);
  opacity: 0;
  transition: opacity .25s;
}
.app.ready { opacity: 1; }
.main {
  min-height: 0;
  display: grid;
  grid-template-columns: clamp(280px, 29vw, 380px) minmax(0, 1fr);
  border-top: 1px solid var(--border);
}
</style>
