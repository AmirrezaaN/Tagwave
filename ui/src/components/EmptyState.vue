<script setup>
import { computed } from 'vue'
import { FilePlus, FolderOpen, ShieldCheck } from '@lucide/vue'
import { state } from '../lib/store.js'
import { t } from '../lib/i18n.js'
import { addFiles, addFolder } from '../lib/actions.js'

const loading = computed(() => Object.values(state.jobs).find((j) => j.kind === 'load' && j.state === 'running'))
</script>

<template>
  <section class="empty">
    <div class="drop">
      <div class="waves" aria-hidden="true">
        <span v-for="i in 23" :key="i" :style="{ '--i': i }" />
      </div>
      <h1>{{ loading ? t('empty.loading', { n: loading.meta?.count || '' }) : t('empty.title') }}</h1>
      <p>{{ t('empty.sub') }}</p>
      <div class="actions">
        <button class="btn gradient lg" @click="addFiles"><FilePlus /> {{ t('a.addFiles') }}</button>
        <span class="or">{{ t('empty.or') }}</span>
        <button class="btn lg" @click="addFolder"><FolderOpen /> {{ t('a.addFolder') }}</button>
      </div>
      <div class="formats"><ShieldCheck /> {{ t('empty.formats') }}</div>
    </div>
  </section>
</template>

<style scoped>
.empty { display: grid; place-items: center; padding: 32px; min-height: 0; }
.drop {
  width: min(760px, 100%); padding: 56px 48px 40px; text-align: center; border-radius: 24px;
  border: 1.5px dashed var(--border-strong);
  background: radial-gradient(600px 260px at 50% 0%, rgba(124, 92, 255, .10), transparent 70%), var(--surface);
  box-shadow: var(--shadow); animation: pop-in .35s var(--ease);
}
.waves { height: 84px; display: flex; align-items: center; justify-content: center; gap: 5px; margin-bottom: 22px; }
.waves span {
  width: 6px; border-radius: 6px; background: var(--grad); background-size: 100% 300%;
  height: calc(14px + (var(--i) * 7 % 60) * 1px);
  animation: wave 1.6s ease-in-out infinite; animation-delay: calc(var(--i) * -0.09s); opacity: .9;
}
@keyframes wave { 0%, 100% { transform: scaleY(.45); } 50% { transform: scaleY(1); } }
h1 { margin: 0 0 10px; font-size: 26px; letter-spacing: -.02em; font-weight: 700; }
p { margin: 0 auto 26px; max-width: 520px; color: var(--muted); font-size: 14px; line-height: 1.7; }
.actions { display: flex; align-items: center; justify-content: center; gap: 12px; }
.or { color: var(--faint); font-size: 12px; }
.formats { margin-top: 28px; font-size: 11.5px; color: var(--faint); display: flex; align-items: center; justify-content: center; gap: 6px; }
.formats svg { width: 14px; height: 14px; color: var(--success); }
</style>
