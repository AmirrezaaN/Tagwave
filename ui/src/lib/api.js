// Thin client for the local Python backend.

const params = new URLSearchParams(location.search)
let token = params.get('t')
try {
  if (token) sessionStorage.setItem('tw-token', token)
  else token = sessionStorage.getItem('tw-token')
} catch { /* storage unavailable */ }
if (!token) token = 'dev'
if (params.get('t')) history.replaceState(null, '', location.pathname)

export class ApiError extends Error {
  constructor(err) {
    super(err?.message || 'Error')
    this.code = err?.code || 'error'
    this.details = err?.details || {}
  }
}

export async function call(method, params = {}) {
  let res
  try {
    res = await fetch('/api/call', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Tagwave-Token': token },
      body: JSON.stringify({ method, params }),
    })
  } catch {
    throw new ApiError({ code: 'offline', message: 'Backend not reachable' })
  }
  if (!res.ok) throw new ApiError({ code: 'http-' + res.status, message: res.statusText })
  const data = await res.json()
  if (!data.ok) throw new ApiError(data.error)
  return data.result
}

export async function uploadImage(bytes) {
  const res = await fetch('/api/upload', {
    method: 'POST',
    headers: { 'Content-Type': 'application/octet-stream', 'X-Tagwave-Token': token },
    body: bytes,
  })
  const data = await res.json()
  if (!data.ok) throw new ApiError(data.error)
  return data.result
}

export function withToken(url) {
  return url + (url.includes('?') ? '&' : '?') + 't=' + encodeURIComponent(token)
}
export const blobUrl = (blob) => (blob ? withToken('/media/blob/' + blob) : '')
export const thumbUrl = (blob, size = 96) => (blob ? withToken(`/media/thumb/${blob}?s=${size}`) : '')

// --------------------------------------------------------------- events + jobs
const listeners = new Set()
const waiters = new Map()
let source = null

export function onEvent(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

function dispatch(msg) {
  if (msg.type === 'job') {
    const job = msg.data
    const w = waiters.get(job.id)
    if (w && job.state !== 'running') {
      waiters.delete(job.id)
      if (job.state === 'error') w.reject(new ApiError(job.error))
      else w.resolve(job)
    }
  }
  for (const fn of listeners) {
    try { fn(msg) } catch (e) { console.error(e) }
  }
}

export function connectEvents() {
  return new Promise((resolve) => {
    if (source) return resolve()
    source = new EventSource(withToken('/api/events'))
    source.onopen = () => resolve()
    source.onmessage = (e) => {
      try { dispatch(JSON.parse(e.data)) } catch (err) { console.error(err) }
    }
    source.onerror = () => { /* EventSource reconnects automatically */ }
    setTimeout(resolve, 1500)
  })
}

// Resolve when a background job finishes. Polling backs up the event stream.
export function waitJob(jobId) {
  if (!jobId) return Promise.resolve(null)
  return new Promise((resolve, reject) => {
    waiters.set(jobId, { resolve, reject })
    const poll = async () => {
      if (!waiters.has(jobId)) return
      try {
        const j = await call('jobs.get', { id: jobId })
        if (j && j.state !== 'running' && waiters.has(jobId)) {
          waiters.delete(jobId)
          if (j.state === 'error') reject(new ApiError(j.error))
          else resolve(j)
          return
        }
      } catch { /* ignore */ }
      setTimeout(poll, 1500)
    }
    setTimeout(poll, 1500)
  })
}
