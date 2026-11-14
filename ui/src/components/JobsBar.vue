<script setup>
import { computed } from 'vue'
import { LoaderCircle, X } from '@lucide/vue'
import { state } from '../lib/store.js'
import { call } from '../lib/api.js'
import { t } from '../lib/i18n.js'

// Long-running background jobs that aren't shown in their own dialog.
const visible = computed(() => Object.values(state.jobs).filter((j) =>
  j.state === 'running' && ((j.kind === 'load' && (j.meta?.count || 0) > 3) || (j.kind === 'save' && (j.meta?.count || 0) > 2) ||
    (j.kind === 'convert' && state.dialog?.name !== 'export'))))

const label = (j) => ({
  load: t('empty.loading', { n: j.meta?.count || '' }),
  save: t('a.save') + '…',
  convert: t('ex.running'),
}[j.kind] || '…')
</script>

<template>
  <div class="jobs">
    <TransitionGroup name="job">
      <div v-for="j in visible" :key="j.id" class="job">
        <LoaderCircle class="spin" />
        <div class="grow">
          <div class="lbl">{{ label(j) }}</div>
          <div class="track"><div class="fill" :style="{ width: Math.round(j.progress * 100) + '%' }" /></div>
        </div>
        <span class="pct ltr">{{ Math.round(j.progress * 100) }}%</span>
        <button class="btn ghost icon sm" @click="call('jobs.cancel', { id: j.id })" :aria-label="t('a.cancel')"><X /></button>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.jobs { position: fixed; bottom: calc(var(--player-h) + 16px); inset-inline-start: 18px; z-index: 190; display: flex; flex-direction: column; gap: 8px; }
.job { width: 320px; display: flex; align-items: center; gap: 10px; padding: 10px 10px 10px 14px; border-radius: 12px; background: var(--surface); border: 1px solid var(--border-strong); box-shadow: var(--shadow-lg); }
.job > svg { width: 16px; height: 16px; color: var(--primary); }
.lbl { font-size: 12.5px; margin-bottom: 6px; }
.track { height: 4px; border-radius: 4px; background: var(--surface-3); overflow: hidden; }
.fill { height: 100%; background: var(--grad); transition: width .2s; }
.pct { font-size: 11px; color: var(--muted); font-variant-numeric: tabular-nums; }
.job-enter-active, .job-leave-active { transition: all .25s var(--ease); }
.job-enter-from, .job-leave-to { opacity: 0; transform: translateY(10px); }
</style>
