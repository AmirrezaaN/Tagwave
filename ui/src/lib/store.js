import { reactive, computed, watch } from 'vue'
import { call, waitJob, onEvent, ApiError } from './api.js'

export const FIELD_KEYS = [
  'title', 'artist', 'album', 'albumartist', 'date', 'genre', 'track', 'tracktotal', 'disc', 'disctotal',
  'composer', 'lyricist', 'conductor', 'comment', 'lyrics', 'bpm', 'publisher', 'copyright', 'encodedby',
  'isrc', 'grouping', 'compilation',
]
export const MIXED = Symbol('mixed')

export const state = reactive({
  ready: false,
  info: {},
  settings: { language: 'en', theme: 'dark' },
  files: [],
  drafts: {},
  selection: [],
  anchor: null,
  filter: '',
  sort: 'added',
  tab: 'tags',
  lyricsSync: false,
  jobs: {},
  saving: false,
  toasts: [],
  dialog: null,
  confirm: null,
  player: { id: null, playing: false, time: 0, duration: 0, loading: false, url: '', version: 0, error: false },
})

const clone = (o) => JSON.parse(JSON.stringify(o))

// ------------------------------------------------------------------ lookups
export const fileMap = computed(() => {
  const m = new Map()
  for (const f of state.files) m.set(f.id, f)
  return m
})

export function draftFrom(file) {
  return {
    fields: clone(file.fields),
    custom: clone(file.custom),
    pictures: clone(file.pictures),
  }
}

function picsSig(pics) {
  return (pics || []).map((p) => `${p.blob}|${p.type}|${p.desc || ''}`).join(',')
}

export function changedFields(id) {
  const f = fileMap.value.get(id)
  const d = state.drafts[id]
  if (!f || !d) return {}
  const out = {}
  for (const k of FIELD_KEYS) {
    if ((d.fields[k] ?? '') !== (f.fields[k] ?? '')) out[k] = d.fields[k] ?? ''
  }
  return out
}

export function isDirty(id) {
  const f = fileMap.value.get(id)
  const d = state.drafts[id]
  if (!f || !d) return false
  for (const k of FIELD_KEYS) if ((d.fields[k] ?? '') !== (f.fields[k] ?? '')) return true
  if (JSON.stringify(d.custom) !== JSON.stringify(f.custom)) return true
  return picsSig(d.pictures) !== picsSig(f.pictures)
}

export const dirtyIds = computed(() => state.files.filter((f) => isDirty(f.id)).map((f) => f.id))

export const selectedFiles = computed(() =>
  state.selection.map((id) => fileMap.value.get(id)).filter(Boolean))

export const editableSelection = computed(() => selectedFiles.value.filter((f) => f.canTag).map((f) => f.id))

function cmp(a, b) {
  return String(a || '').localeCompare(String(b || ''), undefined, { numeric: true, sensitivity: 'base' })
}
const num = (v) => parseInt(v, 10) || 0

export const visibleFiles = computed(() => {
  const q = state.filter.trim().toLowerCase()
  let list = state.files
  if (q) {
    list = list.filter((f) => {
      const d = state.drafts[f.id]?.fields || f.fields
      return [d.title, d.artist, d.album, d.albumartist, f.name].some((v) => (v || '').toLowerCase().includes(q))
    })
  }
  const fl = (f) => state.drafts[f.id]?.fields || f.fields
  const sorted = [...list]
  switch (state.sort) {
    case 'name': sorted.sort((a, b) => cmp(a.name, b.name)); break
    case 'title': sorted.sort((a, b) => cmp(fl(a).title || a.name, fl(b).title || b.name)); break
    case 'artist': sorted.sort((a, b) => cmp(fl(a).artist, fl(b).artist) || cmp(fl(a).album, fl(b).album) ||
      num(fl(a).track) - num(fl(b).track)); break
    case 'album': sorted.sort((a, b) => cmp(fl(a).album, fl(b).album) || num(fl(a).disc) - num(fl(b).disc) ||
      num(fl(a).track) - num(fl(b).track) || cmp(a.name, b.name)); break
    default: break
  }
  return sorted
})

// --------------------------------------------------------------- batch edits
export function commonField(ids, key) {
  if (!ids.length) return ''
  const first = state.drafts[ids[0]]?.fields[key] ?? ''
  for (const id of ids) if ((state.drafts[id]?.fields[key] ?? '') !== first) return MIXED
  return first
}

export function setField(ids, key, value) {
  for (const id of ids) {
    const d = state.drafts[id]
    if (d) d.fields[key] = value
  }
}

export function commonPictures(ids) {
  if (!ids.length) return []
  const sig = picsSig(state.drafts[ids[0]]?.pictures)
  for (const id of ids) if (picsSig(state.drafts[id]?.pictures) !== sig) return null
  return state.drafts[ids[0]].pictures
}

export function setPictures(ids, pics) {
  for (const id of ids) if (state.drafts[id]) state.drafts[id].pictures = clone(pics)
}

export function setFrontCover(ids, pic) {
  for (const id of ids) {
    const d = state.drafts[id]
    if (!d) continue
    const p = { ...clone(pic), type: 3, desc: '' }
    const i = d.pictures.findIndex((x) => x.type === 3)
    if (i >= 0) d.pictures.splice(i, 1, p)
    else d.pictures.unshift(p)
  }
}

export function revert(ids) {
  for (const id of ids) {
    const f = fileMap.value.get(id)
    if (f) state.drafts[id] = draftFrom(f)
  }
}

// --------------------------------------------------------------- selection
export function select(id, { ctrl = false, shift = false } = {}) {
  const order = visibleFiles.value.map((f) => f.id)
  if (shift && state.anchor && order.includes(state.anchor)) {
    const a = order.indexOf(state.anchor)
    const b = order.indexOf(id)
    const range = order.slice(Math.min(a, b), Math.max(a, b) + 1)
    state.selection = ctrl ? [...new Set([...state.selection, ...range])] : range
    return
  }
  if (ctrl) {
    state.selection = state.selection.includes(id)
      ? state.selection.filter((x) => x !== id) : [...state.selection, id]
  } else {
    state.selection = [id]
  }
  state.anchor = id
}

export function selectAll() {
  state.selection = visibleFiles.value.map((f) => f.id)
}

export function moveSelection(delta, extend = false) {
  const order = visibleFiles.value.map((f) => f.id)
  if (!order.length) return
  const cur = state.selection.length ? state.selection[state.selection.length - 1] : null
  let i = cur ? order.indexOf(cur) : -1
  i = Math.max(0, Math.min(order.length - 1, i + delta))
  if (extend) {
    if (!state.anchor) state.anchor = cur || order[i]
    const a = order.indexOf(state.anchor)
    state.selection = order.slice(Math.min(a, i), Math.max(a, i) + 1)
    if (i < a) state.selection.reverse()
  } else {
    state.selection = [order[i]]
    state.anchor = order[i]
  }
  return order[i]
}

// ------------------------------------------------------------------- toasts
let toastId = 0
export function toast(message, kind = 'info', opts = {}) {
  const id = ++toastId
  state.toasts.push({ id, message, kind, action: opts.action || null })
  setTimeout(() => dismissToast(id), opts.timeout || (kind === 'error' ? 7000 : 3800))
  return id
}
export function dismissToast(id) {
  const i = state.toasts.findIndex((t) => t.id === id)
  if (i >= 0) state.toasts.splice(i, 1)
}

export function confirmDialog({ title, body, buttons }) {
  return new Promise((resolve) => {
    state.confirm = { title, body, buttons, resolve: (v) => { state.confirm = null; resolve(v) } }
  })
}

export function openDialog(name, props = {}) {
  state.dialog = { name, props }
}
export function closeDialog() {
  state.dialog = null
}

// -------------------------------------------------------------------- files
export function upsertFiles(files) {
  let added = 0
  for (const f of files) {
    const i = state.files.findIndex((x) => x.id === f.id)
    if (i >= 0) {
      state.files.splice(i, 1, f)
    } else {
      state.files.push(f)
      state.drafts[f.id] = draftFrom(f)
      added++
    }
  }
  if (!state.selection.length && state.files.length) {
    state.selection = [state.files[0].id]
    state.anchor = state.files[0].id
  }
  return added
}

const pendingSave = new Map()

export function applySavedFile(file) {
  const sent = pendingSave.get(file.id)
  const current = state.drafts[file.id]
  const i = state.files.findIndex((x) => x.id === file.id)
  if (i >= 0) state.files.splice(i, 1, file)
  else state.files.push(file)
  // Keep edits the user made while saving was in progress.
  if (!current || sent === undefined || JSON.stringify(current) === sent) state.drafts[file.id] = draftFrom(file)
  pendingSave.delete(file.id)
  if (state.player.id === file.id) state.player.version = file.version
}

export function buildSaveItem(id) {
  const f = fileMap.value.get(id)
  const d = state.drafts[id]
  const item = { id, fields: changedFields(id) }
  if (JSON.stringify(d.custom) !== JSON.stringify(f.custom)) item.custom = d.custom
  if (picsSig(d.pictures) !== picsSig(f.pictures)) {
    item.pictures = d.pictures.map((p) => ({ blob: p.blob, type: p.type, desc: p.desc || '' }))
  }
  return item
}

export async function saveFiles(ids) {
  const list = (ids || dirtyIds.value).filter((id) => isDirty(id))
  if (!list.length || state.saving) return { saved: [], errors: [] }
  state.saving = true
  try {
    const items = list.map(buildSaveItem)
    for (const id of list) pendingSave.set(id, JSON.stringify(state.drafts[id]))
    const { jobId } = await call('files.save', { items })
    const job = await waitJob(jobId)
    return job.result
  } finally {
    state.saving = false
  }
}

export async function removeFiles(ids) {
  await call('files.remove', { ids })
  const drop = new Set(ids)
  state.files = state.files.filter((f) => !drop.has(f.id))
  for (const id of ids) delete state.drafts[id]
  state.selection = state.selection.filter((id) => !drop.has(id))
  if (drop.has(state.player.id)) {
    state.player.id = null
    state.player.playing = false
  }
}

export async function reloadFiles(ids) {
  const res = await call('files.reload', { ids })
  for (const f of res.files) {
    const i = state.files.findIndex((x) => x.id === f.id)
    if (i >= 0) state.files.splice(i, 1, f)
    state.drafts[f.id] = draftFrom(f)
  }
  return res
}

// ----------------------------------------------------------------- settings
export async function updateSettings(patch) {
  state.settings = await call('settings.set', { patch })
}

export function resolvedTheme() {
  const t = state.settings.theme
  if (t === 'system') return matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
  return t === 'light' ? 'light' : 'dark'
}

export function applyTheme() {
  const theme = resolvedTheme()
  document.documentElement.dataset.theme = theme
  const bg = getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()
  call('window.setTheme', { dark: theme === 'dark', background: bg }).catch(() => {})
}

watch(() => dirtyIds.value.length > 0, (dirty) => {
  call('window.setDirty', { dirty }).catch(() => {})
})

// ------------------------------------------------------------------- events
onEvent((msg) => {
  const d = msg.data
  switch (msg.type) {
    case 'files.added': upsertFiles(d.files); break
    case 'files.saved': applySavedFile(d.file); break
    case 'job': state.jobs[d.id] = d; break
    default: break
  }
})

export { ApiError }
