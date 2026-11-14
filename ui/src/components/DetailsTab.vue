<script setup>
import { computed, ref } from 'vue'
import { Copy, FolderSearch, Check } from '@lucide/vue'
import { call } from '../lib/api.js'
import { t } from '../lib/i18n.js'
import { duration, size, kbps, khz } from '../lib/format.js'
import { copyText } from '../lib/actions.js'

const props = defineProps({ files: Array })
const single = computed(() => (props.files.length === 1 ? props.files[0] : null))
const copied = ref(false)

const channels = (n) => (n === 1 ? t('d.mono') : n === 2 ? t('d.stereo') : t('d.ch', { n }))
const rows = computed(() => {
  const f = single.value
  if (!f) {
    const totalSize = props.files.reduce((a, x) => a + (x.size || 0), 0)
    const totalDur = props.files.reduce((a, x) => a + (x.info.duration || 0), 0)
    const codecs = [...new Set(props.files.map((x) => x.info.codec))].join(', ')
    return [
      [t('d.codec'), codecs], [t('d.duration'), duration(totalDur)], [t('d.size'), size(totalSize)],
    ]
  }
  const i = f.info
  const out = [
    [t('d.format'), `${i.container}${i.codecDetail ? ' · ' + i.codecDetail : ''}`],
    [t('d.codec'), i.codec],
    [t('d.quality'), i.lossless ? t('d.lossless') : t('d.lossy'), i.lossless ? 'lossless' : 'lossy'],
    [t('d.bitrate'), kbps(i.bitrate)],
  ]
  if (i.bitrateMode) out.push([t('d.mode'), i.bitrateMode])
  out.push([t('d.sampleRate'), khz(i.sampleRate)])
  if (i.bitsPerSample) out.push([t('d.bits'), t('d.bit', { n: i.bitsPerSample })])
  out.push([t('d.channels'), channels(i.channels)], [t('d.duration'), duration(i.duration)], [t('d.size'), size(f.size)])
  if (f.tagFormat) out.push([t('d.tagFormat'), f.tagFormat])
  if (i.encoder) out.push([t('d.encoder'), i.encoder])
  return out
})

async function copyPath() {
  if (await copyText(single.value.path)) {
    copied.value = true
    setTimeout(() => (copied.value = false), 1500)
  }
}
</script>

<template>
  <div class="details">
    <dl>
      <template v-for="r in rows" :key="r[0]">
        <dt>{{ r[0] }}</dt>
        <dd><span v-if="r[2]" class="badge" :class="r[2]">{{ r[1] }}</span><span v-else class="ltr selectable">{{ r[1] }}</span></dd>
      </template>
    </dl>
    <div v-if="single" class="path card">
      <div class="label">{{ t('d.path') }}</div>
      <div class="p mono selectable ltr" dir="ltr">{{ single.path }}</div>
      <div class="row">
        <button class="btn sm" @click="copyPath"><Check v-if="copied" /><Copy v-else /> {{ copied ? t('d.copied') : t('d.copyPath') }}</button>
        <button class="btn sm ghost" @click="call('system.reveal', { path: single.path })"><FolderSearch /> {{ t('a.reveal') }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.details { max-width: 760px; }
dl { display: grid; grid-template-columns: 180px 1fr; margin: 0 0 18px; border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; background: var(--surface); }
dt, dd { margin: 0; padding: 10px 14px; border-bottom: 1px solid var(--border); }
dt { color: var(--muted); font-size: 12.5px; background: var(--surface-2); }
dd { font-weight: 550; }
dl > :nth-last-child(-n + 2) { border-bottom: 0; }
.path { padding: 14px; }
.p { word-break: break-all; margin-bottom: 10px; color: var(--text-2); }
</style>
