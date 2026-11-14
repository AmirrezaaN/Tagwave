import en from '../locales/en.js'
import fa from '../locales/fa.js'
import { state } from './store.js'

const dicts = { en, fa }

function lookup(dict, key) {
  return key.split('.').reduce((o, k) => (o && o[k] !== undefined ? o[k] : undefined), dict)
}

export function t(key, params) {
  const lang = state.settings.language || 'en'
  let s = lookup(dicts[lang], key)
  if (s === undefined) s = lookup(en, key)
  if (s === undefined) return key
  if (params) {
    for (const [k, v] of Object.entries(params)) s = s.split('{' + k + '}').join(String(v))
  }
  return s
}

export function errorText(err) {
  const code = err?.code || 'error'
  const msg = lookup(dicts[state.settings.language || 'en'], 'e.' + code) || lookup(en, 'e.' + code)
  return msg || err?.message || t('e.error')
}

export function applyLanguage(lang) {
  const html = document.documentElement
  html.lang = lang
  html.dir = lang === 'fa' ? 'rtl' : 'ltr'
}
