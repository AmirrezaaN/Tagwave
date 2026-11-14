<script setup>
import { state } from '../lib/store.js'
import Modal from './Modal.vue'
</script>

<template>
  <Modal v-if="state.confirm" :title="state.confirm.title" width="460px" @close="state.confirm.resolve(null)">
    <p class="body" dir="auto">{{ state.confirm.body }}</p>
    <template #footer>
      <button v-for="(b, i) in state.confirm.buttons" :key="i" class="btn"
              :class="{ primary: b.kind === 'primary', 'danger': b.kind === 'danger' }"
              :autofocus="b.kind === 'primary'" @click="state.confirm.resolve(b.value)">{{ b.label }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.body { margin: 0; color: var(--text-2); line-height: 1.7; white-space: pre-line; }
</style>
