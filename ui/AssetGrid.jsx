import { Play, Stop } from '@openai/apps-sdk-ui/components/Icon'
import { isAudio, LicensePill, Thumb, TYPE_ONE, typeBadge, typeColor } from './shared.jsx'

function shortSpec(card) {
  if (card.is_pack) return card.pack_items ? `${card.pack_items} ${card.pack_label || 'files'}` : 'pack'
  if (card.type === 'model' && card.polycount) {
    const n = card.polycount
    return n >= 1e6 ? `${(n / 1e6).toFixed(1)}M polys` : n >= 1000 ? `${(n / 1000).toFixed(1)}k polys` : `${n} polys`
  }
  if ((card.type === 'texture' || card.type === 'hdri') && card.max_resolution) {
    return `${Math.round(card.max_resolution / 1024)}K`
  }
  if (card.duration) return card.duration >= 60 ? `${Math.floor(card.duration / 60)}:${String(Math.round(card.duration % 60)).padStart(2, '0')} min` : `${card.duration.toFixed(1)} s`
  return ''
}

function Tile({ card, selected, onOpen, tokenRef, playState, onPlay }) {
  const sound = isAudio(card.type)
  const playable = sound && (card.preview_small || card.preview_url)
  return (
    <div className={`ac-tile${selected ? ' is-selected' : ''}${sound ? ' is-sound' : ''}`}>
      <button
        type="button"
        className="ac-tile-main"
        onClick={() => onOpen(card.id)}
        aria-label={`${card.title}, ${TYPE_ONE[card.type] || card.type}, ${card.license_short}, from ${card.source_name}`}
        aria-pressed={selected}
      >
        <Thumb url={card.thumbnail_url} fallbackUrl={card.thumbnail_fallback} alt="" type={card.type} tokenRef={tokenRef} />
        <span className="ac-type-badge">
          <span className="ac-dot" style={{ background: typeColor(card.type) }} />
          {typeBadge(card)}
        </span>
        <span className="ac-tile-body">
          <span className="ac-tile-title" title={card.title}>{card.title}</span>
          <span className="ac-tile-meta">
            <LicensePill card={card} />
            <span>{sound ? card.author : card.source_name}{shortSpec(card) ? ` · ${shortSpec(card)}` : ''}</span>
          </span>
        </span>
      </button>
      {playable && (
        <button
          type="button"
          className={`ac-play${playState ? ` is-${playState}` : ''}`}
          onClick={() => onPlay(card)}
          aria-label={playState ? `Stop ${card.title}` : `Play ${card.title}`}
          title={playState === 'loading' ? 'Loading preview…' : playState ? 'Stop' : 'Play preview'}
        >
          {playState ? <Stop aria-hidden="true" /> : <Play aria-hidden="true" />}
        </button>
      )}
    </div>
  )
}

export function Skeletons({ count = 12 }) {
  return (
    <div className="ac-grid" aria-hidden="true">
      {Array.from({ length: count }, (_, i) => <div key={i} className="ac-skeleton" />)}
    </div>
  )
}

export default function AssetGrid({ results, selectedId, onOpen, tokenRef, playing, onPlay }) {
  return (
    <div className="ac-grid">
      {results.map((card) => (
        <Tile key={card.id} card={card} selected={card.id === selectedId} onOpen={onOpen} tokenRef={tokenRef}
          playState={playing?.id === card.id ? playing.state : null} onPlay={onPlay} />
      ))}
    </div>
  )
}
