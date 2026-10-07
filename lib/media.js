// Previews from the sources' CDNs. The app frame may only load same-origin
// media, so images and audio come through the Möbius proxy with the app token:
// images become data: URLs (cached, at most a few in flight), audio is decoded
// and played with Web Audio (a media element could not use the proxied bytes).

const MAX_IN_FLIGHT = 6
const MAX_CACHED = 600
const PROXY_LIMIT = 2 * 1024 * 1024
const cache = new Map() // url -> Promise<string | null>
const waiting = []
let inFlight = 0

function pump() {
  while (inFlight < MAX_IN_FLIGHT && waiting.length) {
    const job = waiting.shift()
    inFlight += 1
    job().finally(() => { inFlight -= 1; pump() })
  }
}

function proxied(url) {
  return `/api/proxy?url=${encodeURIComponent(url)}`
}

function toDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(blob)
  })
}

export function loadImage(url, tokenRef) {
  if (!url) return Promise.resolve(null)
  if (cache.has(url)) {
    const hit = cache.get(url)
    cache.delete(url)
    cache.set(url, hit) // refresh recency
    return hit
  }
  const promise = new Promise((resolve) => {
    waiting.push(async () => {
      try {
        const response = await fetch(proxied(url), { headers: { Authorization: `Bearer ${tokenRef.current}` } })
        if (!response.ok) throw new Error(`preview ${response.status}`)
        const blob = await response.blob()
        if (!blob.type.startsWith('image/')) throw new Error('not an image')
        // The proxy stops at 2 MB and returns what it has; a cut-off image would show broken, so use the fallback.
        if (blob.size >= PROXY_LIMIT) throw new Error('image larger than the proxy allows')
        resolve(await toDataUrl(blob))
      } catch {
        cache.delete(url) // allow a later retry
        resolve(null)
      }
    })
    pump()
  })
  cache.set(url, promise)
  while (cache.size > MAX_CACHED) cache.delete(cache.keys().next().value)
  return promise
}

let audioContext = null
let current = null

export async function playPreview(url, tokenRef, onEnded) {
  stopPreview()
  const Context = window.AudioContext || window.webkitAudioContext
  if (!Context) throw new Error('This browser cannot play previews.')
  audioContext = audioContext || new Context()
  if (audioContext.state === 'suspended') await audioContext.resume()
  const response = await fetch(proxied(url), { headers: { Authorization: `Bearer ${tokenRef.current}` } })
  if (!response.ok) throw new Error('The preview could not be loaded.')
  const buffer = await audioContext.decodeAudioData(await response.arrayBuffer())
  const source = audioContext.createBufferSource()
  source.buffer = buffer
  source.connect(audioContext.destination)
  source.onended = () => { if (current === source) current = null; onEnded?.() }
  source.start()
  current = source
  return buffer.duration
}

export function stopPreview() {
  if (current) {
    const playing = current
    current = null
    try { playing.stop() } catch { /* already stopped */ }
  }
}
