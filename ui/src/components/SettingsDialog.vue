<script setup>
import { Sun, Moon, Monitor, Languages, Tags, Globe, Info, ShieldCheck } from '@lucide/vue'
import Modal from './Modal.vue'
import { state, closeDialog, updateSettings, toast } from '../lib/store.js'
import { t, errorText } from '../lib/i18n.js'

async function set(patch) {
  try { await updateSettings(patch) } catch (e) { toast(errorText(e), 'error') }
}
const PROVIDERS = { musicbrainz: 'MusicBrainz', itunes: 'iTunes', deezer: 'Deezer' }
function toggleProvider(k, on) {
  const cur = new Set(state.settings.onlineProviders || [])
  on ? cur.add(k) : cur.delete(k)
  set({ onlineProviders: [...cur] })
}
</script>

<template>
  <Modal :title="t('st.title')" width="620px" @close="closeDialog">
    <section>
      <h3><Languages /> {{ t('st.general') }}</h3>
      <div class="item">
        <span>{{ t('st.language') }}</span>
        <div class="seg">
          <button :class="{ on: state.settings.language === 'en' }" @click="set({ language: 'en' })">English</button>
          <button :class="{ on: state.settings.language === 'fa' }" @click="set({ language: 'fa' })">فارسی</button>
        </div>
      </div>
      <div class="item">
        <span>{{ t('st.theme') }}</span>
        <div class="seg">
          <button :class="{ on: state.settings.theme === 'dark' }" @click="set({ theme: 'dark' })"><Moon /> {{ t('st.dark') }}</button>
          <button :class="{ on: state.settings.theme === 'light' }" @click="set({ theme: 'light' })"><Sun /> {{ t('st.light') }}</button>
          <button :class="{ on: state.settings.theme === 'system' }" @click="set({ theme: 'system' })"><Monitor /> {{ t('st.system') }}</button>
        </div>
      </div>
    </section>

    <section>
      <h3><Tags /> {{ t('st.tagging') }}</h3>
      <div class="item col">
        <span>{{ t('st.id3') }}</span>
        <select class="select" :value="state.settings.id3Version" @change="set({ id3Version: $event.target.value })">
          <option value="keep">{{ t('st.id3keep') }}</option>
          <option value="3">{{ t('st.id3v3') }}</option>
          <option value="4">{{ t('st.id3v4') }}</option>
        </select>
      </div>
      <div class="item col">
        <span>{{ t('st.id3v1') }}</span>
        <select class="select" :value="state.settings.id3v1" @change="set({ id3v1: $event.target.value })">
          <option value="keep">{{ t('st.v1keep') }}</option>
          <option value="remove">{{ t('st.v1remove') }}</option>
          <option value="write">{{ t('st.v1write') }}</option>
        </select>
      </div>
      <label class="item">
        <span><span class="inline"><ShieldCheck class="ok" /> {{ t('st.verify') }}</span><small>{{ t('st.verifyHint') }}</small></span>
        <span class="switch"><input type="checkbox" :checked="state.settings.verifyOnSave" @change="set({ verifyOnSave: $event.target.checked })" /><span /></span>
      </label>
      <label class="item">
        <span>{{ t('st.verifyConv') }}</span>
        <span class="switch"><input type="checkbox" :checked="state.settings.verifyConversions" @change="set({ verifyConversions: $event.target.checked })" /><span /></span>
      </label>
      <label class="item">
        <span>{{ t('st.mtime') }}</span>
        <span class="switch"><input type="checkbox" :checked="state.settings.preserveMtime" @change="set({ preserveMtime: $event.target.checked })" /><span /></span>
      </label>
      <label class="item">
        <span>{{ t('st.confirmLossy') }}</span>
        <span class="switch"><input type="checkbox" :checked="state.settings.confirmLossy" @change="set({ confirmLossy: $event.target.checked })" /><span /></span>
      </label>
    </section>

    <section>
      <h3><Globe /> {{ t('st.online') }}</h3>
      <label class="item">
        <span>{{ t('st.onlineOn') }}</span>
        <span class="switch"><input type="checkbox" :checked="state.settings.onlineEnabled" @change="set({ onlineEnabled: $event.target.checked })" /><span /></span>
      </label>
      <div class="item" v-if="state.settings.onlineEnabled">
        <span>{{ t('lk.sources') }}</span>
        <div class="provs">
          <label v-for="(n, k) in PROVIDERS" :key="k" class="check">
            <input type="checkbox" :checked="(state.settings.onlineProviders || []).includes(k)" @change="toggleProvider(k, $event.target.checked)" /> {{ n }}
          </label>
        </div>
      </div>
    </section>

    <section class="about">
      <h3><Info /> {{ t('st.about') }}</h3>
      <div class="brand">
        <img src="/logo.svg" width="40" height="40" alt="" />
        <div>
          <b>Tagwave</b> <span class="muted ltr">{{ t('st.version', { v: state.info.version }) }}</span>
          <p>{{ t('st.aboutText') }}</p>
        </div>
      </div>
      <p class="lic">{{ t('st.licenses') }}</p>
    </section>
  </Modal>
</template>

<style scoped>
section { padding: 4px 0 14px; border-bottom: 1px solid var(--border); margin-bottom: 14px; }
section:last-child { border-bottom: 0; margin-bottom: 0; }
h3 { display: flex; align-items: center; gap: 8px; font-size: 13px; margin: 0 0 10px; color: var(--text-2); }
h3 svg { width: 16px; height: 16px; color: var(--primary); }
.item { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 8px 0; cursor: default; }
label.item { cursor: pointer; }
.item > span:first-child { display: flex; flex-direction: column; gap: 2px; font-size: 13px; }
.item small { color: var(--muted); font-size: 11.5px; }
.item.col { display: grid; grid-template-columns: 1fr 1.3fr; }
.ok { width: 14px; height: 14px; color: var(--success); flex: none; }
.inline { display: flex; align-items: center; gap: 6px; }
.seg { display: flex; background: var(--surface-2); border: 1px solid var(--border); border-radius: 9px; padding: 3px; gap: 3px; }
.seg button { display: flex; align-items: center; gap: 6px; height: 28px; padding: 0 12px; border: 0; background: transparent; border-radius: 6px; color: var(--muted); font-weight: 600; font-size: 12.5px; }
.seg button svg { width: 14px; height: 14px; }
.seg button.on { background: var(--surface-3); color: var(--text); box-shadow: 0 1px 3px rgba(0,0,0,.2); }
.provs { display: flex; gap: 14px; font-size: 12.5px; }
.brand { display: flex; gap: 12px; align-items: flex-start; }
.brand p { margin: 4px 0 0; color: var(--text-2); font-size: 12.5px; }
.lic { font-size: 11.5px; color: var(--faint); margin: 12px 0 0; line-height: 1.6; }
</style>
