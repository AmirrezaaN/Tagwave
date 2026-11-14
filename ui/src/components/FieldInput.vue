<script setup>
import { computed } from 'vue'
import { Undo2 } from '@lucide/vue'
import { state, commonField, setField, fileMap, MIXED } from '../lib/store.js'
import { t } from '../lib/i18n.js'

const props = defineProps({
  ids: { type: Array, required: true },
  field: { type: String, required: true },
  label: String,
  kind: { type: String, default: 'text' },   // text | number | decimal | date | textarea
  list: String,
  rows: { type: Number, default: 3 },
})

const value = computed(() => commonField(props.ids, props.field))
const mixed = computed(() => value.value === MIXED)
const changed = computed(() => props.ids.some((id) =>
  (state.drafts[id]?.fields[props.field] ?? '') !== (fileMap.value.get(id)?.fields[props.field] ?? '')))
const DATE = /^\d{4}(-\d{2}(-\d{2}([T ]\d{2}(:\d{2}(:\d{2})?)?)?)?)?$/
const invalid = computed(() => {
  const v = mixed.value ? '' : String(value.value || '').trim()
  if (!v) return false
  if (props.kind === 'date') return !DATE.test(v)
  if (props.kind === 'decimal') return isNaN(Number(v))
  return false
})

function clean(v) {
  if (props.kind === 'number') return v.replace(/[^\d]/g, '').replace(/[۰-۹]/g, '')
  if (props.kind === 'decimal') return v.replace(/[^\d.]/g, '')
  if (props.kind === 'date') return v.replace(/[^\d\-T: ]/g, '')
  return v
}
function toLatinDigits(v) {
  return v.replace(/[۰-۹]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'.indexOf(d)).replace(/[٠-٩]/g, (d) => '٠١٢٣٤٥٦٧٨٩'.indexOf(d))
}
function onInput(e) {
  let v = e.target.value
  if (props.kind !== 'text' && props.kind !== 'textarea') {
    v = clean(toLatinDigits(v))
    if (v !== e.target.value) e.target.value = v
  }
  setField(props.ids, props.field, v)
}
function restore() {
  for (const id of props.ids) {
    const f = fileMap.value.get(id)
    if (f && state.drafts[id]) state.drafts[id].fields[props.field] = f.fields[props.field] ?? ''
  }
}
const numeric = computed(() => ['number', 'decimal', 'date'].includes(props.kind))
</script>

<template>
  <div class="field" :class="{ changed }">
    <label class="label" v-if="label">
      <span>{{ label }}</span>
      <button v-if="changed" class="undo" @click="restore" :title="t('a.revert')"><Undo2 /></button>
    </label>
    <textarea v-if="kind === 'textarea'" class="textarea" :rows="rows" :value="mixed ? '' : value"
              :placeholder="mixed ? t('ed.mixed') : ''" :class="{ mixed }" dir="auto" spellcheck="false"
              @input="onInput" :disabled="!ids.length" />
    <input v-else class="input" :value="mixed ? '' : value" :placeholder="mixed ? t('ed.mixed') : ''"
           :class="{ mixed, invalid }" :dir="numeric ? 'ltr' : 'auto'" :list="list" spellcheck="false"
           :inputmode="numeric ? 'numeric' : undefined" @input="onInput" :disabled="!ids.length"
           :title="mixed ? t('ed.mixedHint') : ''" />
  </div>
</template>

<style scoped>
.field { min-width: 0; }
.label { display: flex; align-items: center; justify-content: space-between; height: 16px; }
.undo { border: 0; background: transparent; color: var(--primary); padding: 0 2px; display: grid; border-radius: 4px; }
.undo svg { width: 13px; height: 13px; }
.undo:hover { background: var(--primary-soft); }
.changed .input, .changed .textarea { border-color: color-mix(in srgb, var(--primary) 45%, var(--border)); }
.input:disabled, .textarea:disabled { opacity: .5; }
input[dir='ltr'] { text-align: start; }
[dir='rtl'] input[dir='ltr'] { text-align: right; }
</style>
