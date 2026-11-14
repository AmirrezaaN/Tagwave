<script setup>
import { CircleCheck, CircleAlert, Info, X } from '@lucide/vue'
import { state, dismissToast } from '../lib/store.js'
</script>

<template>
  <div class="toasts" aria-live="polite">
    <TransitionGroup name="toast">
      <div v-for="tt in state.toasts" :key="tt.id" class="toast" :class="tt.kind">
        <CircleCheck v-if="tt.kind === 'success'" />
        <CircleAlert v-else-if="tt.kind === 'error'" />
        <Info v-else />
        <span class="msg" dir="auto">{{ tt.message }}</span>
        <button v-if="tt.action" class="btn sm" @click="tt.action.run(); dismissToast(tt.id)">{{ tt.action.label }}</button>
        <button class="x" @click="dismissToast(tt.id)" aria-label="close"><X /></button>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toasts { position: fixed; bottom: calc(var(--player-h) + 16px); inset-inline-end: 18px; z-index: 200; display: flex; flex-direction: column; gap: 8px; align-items: flex-end; pointer-events: none; }
.toast {
  pointer-events: auto; display: flex; align-items: center; gap: 10px; min-width: 260px; max-width: 460px;
  padding: 10px 10px 10px 14px; border-radius: 12px; background: var(--surface); border: 1px solid var(--border-strong);
  box-shadow: var(--shadow-lg); font-size: 13px;
}
.toast > svg { width: 18px; height: 18px; flex: none; color: var(--info); }
.toast.success > svg { color: var(--success); }
.toast.error > svg { color: var(--danger); }
.toast.error { border-color: color-mix(in srgb, var(--danger) 40%, transparent); }
.msg { flex: 1; line-height: 1.45; }
.x { border: 0; background: transparent; color: var(--muted); padding: 4px; border-radius: 6px; display: grid; }
.x:hover { background: var(--hover); color: var(--text); }
.x svg { width: 14px; height: 14px; }
.toast-enter-active, .toast-leave-active { transition: all .25s var(--ease); }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateY(10px) scale(.97); }
</style>
