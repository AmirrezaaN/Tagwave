<script setup>
import { computed } from 'vue'
import { FilePlus, FolderOpen, Search, Save, FileOutput, PenLine, Globe, Settings, X, LoaderCircle } from '@lucide/vue'
import { state, dirtyIds, openDialog, editableSelection } from '../lib/store.js'
import { t } from '../lib/i18n.js'
import { addFiles, addFolder } from '../lib/actions.js'

const props = defineProps({ onSave: Function })
const hasSel = computed(() => state.selection.length > 0)
const single = computed(() => editableSelection.value.length === 1)
</script>

<template>
  <header class="top">
    <div class="brand">
      <img src="/logo.svg" alt="" width="28" height="28" />
      <div class="brand-text">
        <strong>Tagwave</strong>
        <span>{{ t('app.tagline') }}</span>
      </div>
    </div>

    <div class="group">
      <button class="btn" @click="addFiles" :title="t('a.addFiles') + ' (Ctrl+O)'"><FilePlus /> {{ t('a.addFiles') }}</button>
      <button class="btn ghost" @click="addFolder" :title="t('a.addFolder') + ' (Ctrl+Shift+O)'"><FolderOpen /> <span class="hide-xs">{{ t('a.addFolder') }}</span></button>
    </div>

    <label class="search" v-if="state.files.length">
      <Search />
      <input id="tw-search" v-model="state.filter" :placeholder="t('top.search')" spellcheck="false" dir="auto" />
      <button v-if="state.filter" class="clear" @click="state.filter = ''" :aria-label="t('a.clear')"><X /></button>
    </label>
    <div class="grow" />

    <div class="group">
      <button class="btn ghost" :disabled="!single" @click="openDialog('lookup')" :title="t('a.lookup')"><Globe /> <span class="hide-sm">{{ t('a.lookup') }}</span></button>
      <button class="btn ghost" :disabled="!hasSel" @click="openDialog('rename')" :title="t('a.rename') + ' (F2)'"><PenLine /> <span class="hide-sm">{{ t('a.rename') }}</span></button>
      <button class="btn ghost" :disabled="!hasSel" @click="openDialog('export')" :title="t('a.export') + ' (Ctrl+E)'"><FileOutput /> {{ t('a.export') }}</button>
      <button class="btn gradient save" :disabled="!dirtyIds.length || state.saving" @click="props.onSave()" :title="t('a.saveAll') + ' (Ctrl+S)'">
        <LoaderCircle v-if="state.saving" class="spin" /><Save v-else />
        {{ t('a.save') }}
        <span v-if="dirtyIds.length" class="count">{{ dirtyIds.length }}</span>
      </button>
      <button class="btn ghost icon" @click="openDialog('settings')" :title="t('a.settings')" :aria-label="t('a.settings')"><Settings /></button>
    </div>
  </header>
</template>

<style scoped>
.top {
  display: flex; align-items: center; gap: 14px; padding: 0 16px;
  background: var(--glass); backdrop-filter: blur(18px) saturate(1.4);
  position: relative; z-index: 5;
}
.brand { display: flex; align-items: center; gap: 10px; padding-inline-end: 6px; }
.brand img { filter: drop-shadow(0 4px 10px rgba(99, 102, 241, .45)); }
.brand-text { display: flex; flex-direction: column; line-height: 1.1; }
.brand-text strong { font-size: 15px; letter-spacing: -.01em; }
.brand-text span { font-size: 11px; color: var(--muted); white-space: nowrap; }
.group { display: flex; align-items: center; gap: 6px; }
.search {
  position: relative; display: flex; align-items: center; flex: 0 1 380px; min-width: 200px;
  height: 34px; padding: 0 10px; gap: 8px; border-radius: 10px;
  background: var(--input); border: 1px solid var(--border); transition: .15s;
}
.search:focus-within { border-color: var(--primary); box-shadow: 0 0 0 3px var(--primary-soft); background: var(--input-focus); }
.search svg { width: 15px; height: 15px; color: var(--muted); flex: none; }
.search input { flex: 1; min-width: 0; border: 0; outline: 0; background: transparent; height: 100%; user-select: text; }
.search input::placeholder { color: var(--faint); }
.clear { border: 0; background: transparent; color: var(--muted); display: grid; place-items: center; padding: 2px; border-radius: 5px; }
.clear:hover { background: var(--hover); color: var(--text); }
.save { min-width: 96px; }
.count {
  min-width: 18px; height: 18px; padding: 0 5px; border-radius: 9px; font-size: 11px; font-weight: 700;
  display: inline-grid; place-items: center; background: rgba(255, 255, 255, .25);
}
@media (max-width: 1220px) { .hide-sm { display: none; } }
@media (max-width: 1100px) {
  .brand-text span { display: none; }
  .search { min-width: 140px; }
  .top { gap: 10px; padding: 0 12px; }
}
@media (max-width: 1020px) { .hide-xs { display: none; } }
</style>
