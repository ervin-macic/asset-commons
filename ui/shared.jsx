import { useEffect, useRef, useState } from 'react'
import { Cube, Grid, ImageSquare, Music, SoundOnReadOutLoudSpeaker, Storyboard, Sun, Widget } from '@openai/apps-sdk-ui/components/Icon'
import { loadImage } from '../lib/media.js'

export const TYPE_ORDER = ['texture', 'model', 'hdri', 'sound', 'music', 'animation', 'sprite', 'ui']
export const TYPE_LABELS = {
  texture: 'Textures', model: 'Models', hdri: 'HDRIs', sound: 'Sounds', music: 'Music', animation: 'Animations', sprite: '2D', ui: 'UI',
}
export const TYPE_ONE = { texture: 'Texture', model: 'Model', hdri: 'HDRI', sound: 'Sound', music: 'Music', animation: 'Animation', sprite: '2D art', ui: 'UI kit' }
const TYPE_ICONS = { texture: Grid, model: Cube, hdri: Sun, sound: SoundOnReadOutLoudSpeaker, music: Music, animation: Storyboard, sprite: ImageSquare, ui: Widget }

// Sound effects and music share the audio presentation (waveform tiles, play buttons).
export function isAudio(type) {
  return type === 'sound' || type === 'music'
}

export function TypeIcon({ type, ...props }) {
  const Icon = TYPE_ICONS[type] || Grid
  return <Icon aria-hidden="true" {...props} />
}

export function typeBadge(card) {
  const base = TYPE_ONE[card.type] || card.type
  const kind = card.is_pack && card.type !== 'ui' ? `${base} pack` : base
  return (card.extra_types || []).includes('animation') && card.type !== 'animation' ? `${kind} · animated` : kind
}

export function typeColor(type) {
  return `var(--ac-${type in TYPE_ICONS ? type : 'texture'})`
}

export function licenseTier(card) {
  return card.license_tier || card.license_detail?.tier || (card.attribution_required ? 'attribution' : 'public-domain')
}

export function LicensePill({ card }) {
  return (
    <span className={`ac-lic tier-${licenseTier(card)}`} title={card.attribution_required ? 'Attribution required' : 'No attribution required'}>
      {card.license_short}
    </span>
  )
}

export function formatBytes(bytes) {
  if (!bytes) return '—'
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(bytes >= 100 * 1024 ** 2 ? 0 : 1)} MB`
  return `${Math.max(1, Math.round(bytes / 1024))} KB`
}

// A preview image fetched through the proxy once it scrolls near the viewport.
export function Thumb({ url, fallbackUrl, alt, tokenRef, type, eager = false, className = '' }) {
  const holder = useRef(null)
  const [visible, setVisible] = useState(eager)
  const [src, setSrc] = useState(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (eager || visible || !holder.current) return undefined
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        setVisible(true)
        observer.disconnect()
      }
    }, { rootMargin: '400px 0px' })
    observer.observe(holder.current)
    return () => observer.disconnect()
  }, [eager, visible])

  useEffect(() => {
    let live = true
    setSrc(null)
    setFailed(false)
    if (!visible || !url) return undefined
    loadImage(url, tokenRef)
      .then((data) => (data || !fallbackUrl || fallbackUrl === url ? data : loadImage(fallbackUrl, tokenRef)))
      .then((data) => {
        if (!live) return
        if (data) setSrc(data)
        else setFailed(true)
      })
    return () => { live = false }
  }, [url, fallbackUrl, visible, tokenRef])

  return (
    <span ref={holder} className={`ac-thumb ${className}`}>
      {(!src || failed) && (
        <span className="ac-thumb-fallback"><TypeIcon type={type} /></span>
      )}
      {src && <img src={src} alt={alt || ''} className="is-ready" draggable="false" />}
    </span>
  )
}

export function EmptyState({ icon, title, children, action }) {
  return (
    <div className="ac-empty" role="status">
      <div className="ac-empty-mark" aria-hidden="true">{icon}</div>
      <div className="ac-empty-title">{title}</div>
      <p>{children}</p>
      {action}
    </div>
  )
}
