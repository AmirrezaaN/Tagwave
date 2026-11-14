// User-level actions shared by several components.
import { call, uploadImage } from './api.js'
import { errorText } from './i18n.js'
import { toast } from './store.js'

export async function addFiles() {
  try {
    await call('dialog.openFiles')
  } catch (e) {
    if (e.code === 'no-native') return promptPaths()
    toast(errorText(e), 'error')
  }
}

export async function addFolder() {
  try {
    await call('dialog.openFolder')
  } catch (e) {
    if (e.code === 'no-native') return promptPaths()
    toast(errorText(e), 'error')
  }
}

// Development fallback when running in a normal browser (no native dialogs).
async function promptPaths() {
  const v = window.prompt('Paths (one per line or separated by |):')
  if (!v) return
  const paths = v.split(/\r?\n|\|/).map((s) => s.trim()).filter(Boolean)
  try { await call('files.add', { paths }) } catch (e) { toast(errorText(e), 'error') }
}

export async function pickImage() {
  try {
    const res = await call('images.pick', { multiple: false })
    if (res.errors?.length) toast(errorText(res.errors[0].error), 'error')
    return res.images?.[0] || null
  } catch (e) {
    if (e.code === 'no-native') return pickImageBrowser()
    toast(errorText(e), 'error')
    return null
  }
}

function pickImageBrowser() {
  return new Promise((resolve) => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'image/*'
    input.onchange = async () => {
      const file = input.files?.[0]
      if (!file) return resolve(null)
      resolve(await imageFromFile(file))
    }
    input.click()
  })
}

export async function imageFromFile(file) {
  try {
    return await uploadImage(await file.arrayBuffer())
  } catch (e) {
    toast(errorText(e), 'error')
    return null
  }
}

export async function imageFromClipboardEvent(e) {
  const items = [...(e.clipboardData?.items || [])]
  const item = items.find((i) => i.kind === 'file' && i.type.startsWith('image/'))
  if (!item) return null
  const file = item.getAsFile()
  return file ? imageFromFile(file) : null
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}
