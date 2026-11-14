<script setup>
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { X } from '@lucide/vue'

const props = defineProps({
  title: String, subtitle: String, width: { type: String, default: '640px' },
  closable: { type: Boolean, default: true }, bodyClass: String,
})
const emit = defineEmits(['close'])
const card = ref(null)

function onKey(e) {
  if (e.key === 'Escape' && props.closable) { e.stopPropagation(); emit('close') }
}
onMounted(() => {
  window.addEventListener('keydown', onKey, true)
  card.value?.querySelector('[autofocus]')?.focus()
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey, true))
</script>

<template>
  <Teleport to="body">
    <div class="overlay" @mousedown.self="closable && emit('close')">
      <div ref="card" class="modal" :style="{ width }" role="dialog" aria-modal="true">
        <header>
          <div class="titles">
            <h2>{{ title }}</h2>
            <p v-if="subtitle">{{ subtitle }}</p>
          </div>
          <slot name="head" />
          <button v-if="closable" class="btn ghost icon sm" @click="emit('close')" aria-label="close"><X /></button>
        </header>
        <div class="body" :class="bodyClass"><slot /></div>
        <footer v-if="$slots.footer"><slot name="footer" /></footer>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.overlay {
  position: fixed; inset: 0; z-index: 150; display: grid; place-items: center; padding: 24px;
  background: rgba(5, 6, 10, .55); backdrop-filter: blur(6px); animation: fade-in .15s;
}
:root[data-theme='light'] .overlay { background: rgba(20, 24, 40, .28); }
.modal {
  max-width: 100%; max-height: calc(100vh - 48px); display: flex; flex-direction: column;
  background: var(--surface); border: 1px solid var(--border-strong); border-radius: 18px;
  box-shadow: var(--shadow-lg); animation: pop-in .2s var(--ease); overflow: hidden;
}
header { display: flex; align-items: flex-start; gap: 12px; padding: 18px 20px 12px; }
.titles { flex: 1; min-width: 0; }
h2 { margin: 0; font-size: 17px; font-weight: 680; letter-spacing: -.01em; }
p { margin: 3px 0 0; color: var(--muted); font-size: 12.5px; }
.body { padding: 4px 20px 18px; overflow: auto; min-height: 0; }
footer { display: flex; align-items: center; justify-content: flex-end; gap: 8px; padding: 14px 20px; border-top: 1px solid var(--border); background: var(--surface-2); }
</style>
