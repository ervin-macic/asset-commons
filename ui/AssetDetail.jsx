import { useEffect, useState } from 'react'
import { Copy, ExternalLink, Play, Robot, Stop, XCrossed } from '@openai/apps-sdk-ui/components/Icon'
import { playPreview, stopPreview } from '../lib/media.js'
import { formatBytes, isAudio, licenseTier, LicensePill, Thumb, TYPE_ONE, TypeIcon } from './shared.jsx'
import { FieldNotes } from './ToolViews.jsx'

function Contents({ asset, onCopy }) {
  const items = asset.attributes?.contents || []
  const [all, setAll] = useState(false)
  if (!items.length) return null
  const shown = all ? items : items.slice(0, 40)
  const example = items.find((name) => !/\s/.test(name)) || items[0]
  const prompt = `Download just the “${example}” model from the Asset Commons pack ${asset.id} into this project with asset_commons_download pick=["${example}"].`
  return (
    <section aria-label="What is inside">
      <h3 className="ac-section-label">What’s inside ({items.length})</h3>
      <div className="ac-contents">{shown.map((name) => <span key={name}>{name}</span>)}</div>
      <div className="ac-agent-actions">
        {items.length > 40 && <button type="button" className="ac-btn is-ghost is-small" onClick={() => setAll((v) => !v)}>{all ? 'Show fewer' : `Show all ${items.length}`}</button>}
        {!asset.attributes?.manual_download && (
          <button type="button" className="ac-btn is-small" onClick={() => onCopy(prompt, 'Prompt copied')}><Copy aria-hidden="true" />Copy “just one item” prompt</button>
        )}
      </div>
    </section>
  )
}

const ENGINES = [
  ['godot', 'Godot 4'], ['threejs', 'three.js'], ['unity', 'Unity'], ['unreal', 'Unreal'], ['blender', 'Blender'],
]
const VISIBLE_VARIANTS = 6

function metres(values) {
  return values.map((v) => (Math.round(v * 100) / 100).toString()).join(' × ') + ' m'
}

function Specs({ asset }) {
  const items = []
  const attributes = asset.attributes || {}
  if (attributes.pack) items.push(['Pack', attributes.items ? `${attributes.items} ${attributes.item_label || 'files'}` : 'yes'])
  if ((asset.extra_types || []).includes('animation') || attributes.animated) items.push(['Animated', 'yes'])
  if (attributes.textured === true) items.push(['Textured', 'yes'])
  if (attributes.series) items.push(['Series', attributes.series])
  if (attributes.version) items.push(['Version', attributes.version])
  if (asset.polycount) items.push(['Polys', asset.polycount.toLocaleString()])
  if (asset.dimensions_m) items.push(['Size', metres(asset.dimensions_m)])
  if (asset.attributes?.real_size_m) items.push(['Covers', metres(asset.attributes.real_size_m)])
  if (asset.max_resolution) items.push(['Up to', `${Math.round(asset.max_resolution / 1024)}K`])
  if (asset.duration) {
    const seconds = asset.duration
    items.push(['Length', seconds >= 60 ? `${Math.floor(seconds / 60)}:${String(Math.round(seconds % 60)).padStart(2, '0')}` : `${seconds.toFixed(1)} s`])
  }
  if (asset.attributes?.maps?.length) items.push(['Maps', asset.attributes.maps.length])
  if (asset.attributes?.dynamic_range_ev) items.push(['Range', `${asset.attributes.dynamic_range_ev} EV`])
  const original = asset.attributes?.original
  if (original?.type) {
    const parts = [original.type.toUpperCase()]
    if (original.samplerate) parts.push(`${(original.samplerate / 1000).toFixed(1).replace(/\.0$/, '')} kHz`)
    if (original.channels) parts.push(original.channels === 1 ? 'mono' : original.channels === 2 ? 'stereo' : `${original.channels} ch`)
    if (original.filesize) parts.push(formatBytes(original.filesize))
    items.push(['Original', parts.join(' · ')])
  }
  if (asset.attributes?.rating) items.push(['Rating', `${asset.attributes.rating} / 5`])
  if (asset.attributes?.source_downloads) items.push(['Downloads', asset.attributes.source_downloads.toLocaleString()])
  if (asset.attributes?.favorites) items.push(['Favourites', asset.attributes.favorites.toLocaleString()])
  if (asset.formats?.length) items.push([asset.source === 'freesound' ? 'Previews' : 'Formats', asset.formats.map((f) => f.toUpperCase()).join(', ')])
  if (!items.length) return null
  return (
    <div className="ac-specs">
      {items.map(([label, value]) => <span key={label} className="ac-spec"><em>{label}</em>{value}</span>)}
    </div>
  )
}

function AudioButton({ url, tokenRef }) {
  const [state, setState] = useState('idle')
  useEffect(() => () => stopPreview(), [])
  async function toggle() {
    if (state === 'playing' || state === 'loading') { stopPreview(); setState('idle'); return }
    setState('loading')
    try {
      await playPreview(url, tokenRef, () => setState('idle'))
      setState('playing')
    } catch {
      setState('error')
    }
  }
  return (
    <button type="button" className="ac-btn is-primary" onClick={toggle} aria-pressed={state === 'playing'}>
      {state === 'playing' ? <Stop aria-hidden="true" /> : <Play aria-hidden="true" />}
      {state === 'loading' ? 'Loading…' : state === 'playing' ? 'Stop' : state === 'error' ? 'Preview failed — retry' : 'Play preview'}
    </button>
  )
}

function Variants({ asset, onCopy }) {
  const [all, setAll] = useState(false)
  const variants = [...asset.downloads].sort((a, b) =>
    (b.id === asset.default_variant) - (a.id === asset.default_variant))
  const shown = all ? variants : variants.slice(0, VISIBLE_VARIANTS)
  const manual = asset.attributes?.manual_download
  if (!variants.length && manual) {
    return (
      <div className="ac-variants">
        <div className="ac-variant">
          <div className="ac-variant-label">
            {manual.label}
            <small>{manual.note} Agents can’t fetch this pack on their own.</small>
          </div>
          <a className="ac-btn is-small" href={manual.url} target="_blank" rel="noopener noreferrer"
            aria-label={`Open the download page for ${asset.title}`}><ExternalLink aria-hidden="true" />Open</a>
        </div>
      </div>
    )
  }
  if (!variants.length) {
    return (
      <p className="ac-desc">
        {asset.downloads_error || (asset.details_pending
          ? `Reading the file list from ${asset.source_name}… (the site asks for ten seconds between requests, so this can take a moment)`
          : 'No downloadable files are listed for this asset.')}
      </p>
    )
  }
  return (
    <div className="ac-variants">
      {shown.map((variant) => {
        const urls = variant.files.map((f) => f.url).join('\n')
        return (
          <div key={variant.id} className={`ac-variant${variant.id === asset.default_variant ? ' is-default' : ''}`}>
            <div className="ac-variant-label">
              {variant.label}
              <small>
                {variant.id === asset.default_variant ? 'Recommended · ' : ''}
                {variant.files.length > 1 ? `${variant.files.length} files` : variant.archive === 'zip' ? 'zip archive' : '1 file'}
                {' · '}<code>{variant.id}</code>
              </small>
            </div>
            <span className="ac-variant-size">{variant.size ? formatBytes(variant.size) : 'preview'}</span>
            <button type="button" className="ac-btn is-small" onClick={() => onCopy(urls, variant.files.length > 1 ? 'Links copied' : 'Link copied')}
              aria-label={`Copy download link${variant.files.length > 1 ? 's' : ''} for ${variant.label}`}>
              <Copy aria-hidden="true" />{variant.files.length > 1 ? 'Links' : 'Link'}
            </button>
          </div>
        )
      })}
      {asset.source === 'freesound' && asset.attributes?.original?.type && (
        <div className="ac-variant">
          <div className="ac-variant-label">
            Original {asset.attributes.original.type.toUpperCase()}
            <small>Freesound only lets signed-in people download originals</small>
          </div>
          <span className="ac-variant-size">{formatBytes(asset.attributes.original.filesize)}</span>
          <a className="ac-btn is-small" href={asset.source_url} target="_blank" rel="noopener noreferrer"
            aria-label="Open the original on Freesound"><ExternalLink aria-hidden="true" />Open</a>
        </div>
      )}
      {variants.length > VISIBLE_VARIANTS && (
        <div className="ac-variants-more">
          <button type="button" className="ac-btn is-ghost is-small" onClick={() => setAll((v) => !v)}>
            {all ? 'Show fewer' : `Show all ${variants.length} downloads`}
          </button>
        </div>
      )}
    </div>
  )
}

function ImportNotes({ notes, engine, onEngine }) {
  const available = ENGINES.filter(([id]) => notes?.[id]?.length)
  if (!available.length) return null
  const active = notes[engine] ? engine : available[0][0]
  return (
    <section className="ac-notes" aria-label="Import notes">
      <h3 className="ac-section-label">Import notes</h3>
      <div className="ac-seg" role="tablist" aria-label="Engine">
        {available.map(([id, label]) => (
          <button key={id} type="button" role="tab" aria-selected={active === id}
            className={`ac-seg-btn${active === id ? ' is-active' : ''}`} onClick={() => onEngine(id)}>{label}</button>
        ))}
      </div>
      <ol>{notes[active].map((step, i) => <li key={i}>{step}</li>)}</ol>
    </section>
  )
}

export default function AssetDetail({ asset, loading, error, onClose, onOpen, onTag, onCopy, onRetry, tokenRef,
  engine, onEngine, api, onChanged }) {
  if (loading || !asset) {
    return (
      <aside className="ac-detail" aria-label="Asset details" aria-busy="true">
        <div className="ac-detail-top">
          <span className="ac-crumb">Loading…</span>
          <button type="button" className="ac-btn is-ghost ac-icon-btn" onClick={onClose} aria-label="Close details"><XCrossed /></button>
        </div>
        {error ? (
          <div className="ac-detail-main">
            <p className="ac-error-text">{error}</p>
            <button type="button" className="ac-btn" onClick={onRetry}>Try again</button>
          </div>
        ) : (
          <div className="ac-hero"><div className="ac-skeleton" style={{ aspectRatio: 'auto', height: '100%', borderRadius: 0 }} /></div>
        )}
      </aside>
    )
  }
  const tier = licenseTier(asset)
  const attribution = asset.attribution_required
  const variant = asset.default_variant
  const manualDownload = asset.attributes?.manual_download
  const prompt = manualDownload
    ? `Help me use the Asset Commons pack ${asset.id} (${asset.title}) in this project. It has to be downloaded by hand from ${manualDownload.url}; tell me where to unzip it, then set it up and keep the credits.`
    : `Use the Asset Commons asset ${asset.id}${variant ? ` (${variant})` : ''} in this project: download it with asset_commons_download into the project's assets folder, set it up, and keep the credits.`
  return (
    <aside className="ac-detail" aria-label={`${asset.title} details`}>
      <div className="ac-detail-top">
        <span className="ac-crumb"><TypeIcon type={asset.type} width={15} height={15} />{TYPE_ONE[asset.type]} · {asset.source_name}</span>
        <span style={{ display: 'flex', gap: 4 }}>
          {asset.source_url && (
            <a className="ac-btn is-ghost is-small" href={asset.source_url} target="_blank" rel="noopener noreferrer">
              <ExternalLink aria-hidden="true" />Source
            </a>
          )}
          <button type="button" className="ac-btn is-ghost ac-icon-btn" onClick={onClose} aria-label="Close details"><XCrossed /></button>
        </span>
      </div>
      <Thumb url={isAudio(asset.type) ? asset.thumbnail_url : asset.preview_url || asset.thumbnail_url}
        fallbackUrl={asset.thumbnail_url} alt={asset.title} type={asset.type} tokenRef={tokenRef}
        eager className={`ac-hero${asset.type === 'hdri' ? ' is-hdri' : isAudio(asset.type) ? ' is-sound' : ''}`} />
      <div className="ac-detail-main">
        <div>
          <h2>{asset.title}</h2>
          <p className="ac-byline">
            {asset.details_pending && !asset.authors?.length ? 'on ' : `by ${asset.author} · `}{asset.source_url
              ? <a href={asset.source_url} target="_blank" rel="noopener noreferrer">{asset.source_name}</a>
              : asset.source_name}
            {asset.details_pending ? ' · reading the author and files…' : ''}
            {asset.pulls ? ` · pulled ${asset.pulls}× by agents` : ''}
          </p>
          {(asset.attributes?.video || asset.attributes?.support_url) && (
            <p className="ac-byline">
              {asset.attributes.video && (
                <a href={asset.attributes.video.replace('/embed/', '/watch?v=')} target="_blank" rel="noopener noreferrer">Watch the preview video</a>
              )}
              {asset.attributes.video && asset.attributes.support_url ? ' · ' : ''}
              {asset.attributes.support_url && (
                <a href={asset.attributes.support_url} target="_blank" rel="noopener noreferrer">Support {asset.author}</a>
              )}
            </p>
          )}
        </div>
        {isAudio(asset.type) && asset.preview_url && (
          <AudioButton tokenRef={tokenRef}
            url={(asset.duration || 0) > 120 && asset.preview_small ? asset.preview_small : asset.preview_url} />
        )}
        {asset.description && <p className="ac-desc">{asset.description}</p>}

        <section className={`ac-license-card tier-${tier}`} aria-label="Licence">
          <div className="ac-license-head">
            <strong>{asset.license_detail.name}</strong>
            <LicensePill card={asset} />
          </div>
          <p>{asset.license_detail.summary}</p>
          <div className="ac-credit">
            <code>{asset.credit}</code>
            <button type="button" className="ac-btn is-small" onClick={() => onCopy(asset.credit, 'Credit copied')}
              aria-label="Copy credit line"><Copy aria-hidden="true" /></button>
          </div>
          {!attribution && <p>Crediting is optional; Asset Commons still records it so projects keep provenance.</p>}
          {(asset.source_notes || []).map((note) => <p key={note} className="ac-source-note">{note}</p>)}
        </section>

        <Specs asset={asset} />

        <section className="ac-agent-box" aria-label="Use with an agent">
          <p><Robot aria-hidden="true" width={14} height={14} style={{ verticalAlign: '-2px', marginRight: 6 }} />
            Any agent on this Möbius can pull it with the Asset Commons tools. Paste this into a chat:</p>
          <code>{prompt}</code>
          <div className="ac-agent-actions">
            <button type="button" className="ac-btn is-small" onClick={() => onCopy(prompt, 'Prompt copied')}><Copy aria-hidden="true" />Copy prompt</button>
            <button type="button" className="ac-btn is-small is-ghost" onClick={() => onCopy(asset.id, 'Asset id copied')}>Copy id</button>
          </div>
        </section>

        <section aria-label="Downloads">
          <h3 className="ac-section-label">Downloads</h3>
          <Variants asset={asset} onCopy={onCopy} />
        </section>

        <Contents asset={asset} onCopy={onCopy} />

        <ImportNotes notes={asset.import_notes} engine={engine} onEngine={onEngine} />

        {api && <FieldNotes api={api} target={asset.id} notes={asset.field_notes} onChanged={onChanged} />}

        {asset.tags?.length > 0 && (
          <section aria-label="Tags">
            <h3 className="ac-section-label">Tags</h3>
            <div className="ac-tags">
              {asset.tags.slice(0, 18).map((tag) => (
                <button key={tag} type="button" className="ac-chip" onClick={() => onTag(tag)}>{tag}</button>
              ))}
            </div>
          </section>
        )}

        {asset.related?.length > 0 && (
          <section aria-label="Related assets">
            <h3 className="ac-section-label">Related</h3>
            <div className="ac-related">
              {asset.related.slice(0, 8).map((item) => (
                <button key={item.id} type="button" onClick={() => onOpen(item.id)} aria-label={item.title} title={item.title}>
                  <Thumb url={item.thumbnail_url} alt="" type={item.type} tokenRef={tokenRef} />
                </button>
              ))}
            </div>
          </section>
        )}
      </div>
    </aside>
  )
}
