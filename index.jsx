import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Globe, InfoCircle, Robot, Search, Tools, XCrossed } from '@openai/apps-sdk-ui/components/Icon'
import { CSS } from './theme.js'
import { createApi } from './lib/api.js'
import { playPreview, stopPreview } from './lib/media.js'
import AssetGrid, { Skeletons } from './ui/AssetGrid.jsx'
import AssetDetail from './ui/AssetDetail.jsx'
import AgentSheet from './ui/AgentSheet.jsx'
import SourcesSheet from './ui/SourcesSheet.jsx'
import { ToolDetail, ToolStrip, ToolsView } from './ui/ToolViews.jsx'
import { EmptyState, TYPE_LABELS, TYPE_ORDER, typeColor } from './ui/shared.jsx'

const PAGE = 48
const EXAMPLES = ['mossy rock texture, cc0, 2k', 'sunset sky hdri', 'wooden chair under 10k tris', 'rusty metal', 'brick wall 4k',
  'footsteps on gravel sound', 'rain ambience under 60 s', 'calm loopable music', '8-bit battle music', 'pixel art dungeon tileset']
const PENDING_RETRY_MS = 8000 // an entry whose page is still being read is fetched again after this
const PENDING_TRIES = 8
const LICENSES = [['', 'Any free licence'], ['public-domain', 'CC0 / public domain'], ['attribution', 'Attribution licences']]
const SORTS = [['', 'Best match'], ['popular', 'Most popular'], ['newest', 'Newest'], ['name', 'A–Z']]

const LICENSE_WORDS = { 'CC0-1.0': 'CC0', 'PDM-1.0': null }
const STYLE_WORDS = { 'low-poly': 'low-poly', stylized: 'stylized', pixel: 'pixel art', toon: 'toon', realistic: 'realistic', 'hand-painted': 'hand-painted' }

// A short plain-language echo of the filters the server read from the words.
function understood(interpreted, chosenType, chosenLicense) {
  if (!interpreted) return ''
  const parts = []
  if (!chosenType && interpreted.type?.length) parts.push(interpreted.type.map((t) => TYPE_LABELS[t] || t).join(' or '))
  if (!chosenLicense && interpreted.license?.length) {
    const names = interpreted.license.map((l) => (l in LICENSE_WORDS ? LICENSE_WORDS[l] : l)).filter(Boolean)
    if (names.length) parts.push(names.join(' / '))
  }
  if (interpreted.style?.length) parts.push(interpreted.style.map((s) => STYLE_WORDS[s] || s).join(' / '))
  if (interpreted.min_resolution) parts.push(`${Math.round(interpreted.min_resolution / 1000)}K or larger`)
  if (interpreted.max_polycount) parts.push(`under ${Number(interpreted.max_polycount).toLocaleString()} polys`)
  if (interpreted.max_duration) parts.push(`under ${interpreted.max_duration} s`)
  if (interpreted.concepts?.length && parts.length) {
    parts.push(interpreted.concepts.map((c) => `“${c}”`).join(' + '))
  }
  return parts.length > 1 ? parts.join(' · ') : ''
}

function signal(name, payload) {
  try { window.mobius?.signal?.(name, payload) } catch { /* telemetry is best-effort */ }
}

export default function App({ appId, token }) {
  const tokenRef = useRef(token)
  tokenRef.current = token
  const api = useMemo(() => createApi(appId, tokenRef), [appId])

  const [overview, setOverview] = useState(null)
  const [service, setService] = useState('loading') // loading | ready | unavailable
  const [serviceError, setServiceError] = useState('')
  const [input, setInput] = useState('')
  const [query, setQuery] = useState('')
  const [type, setType] = useState('')
  const [license, setLicense] = useState('')
  const [sort, setSort] = useState('')
  const [page, setPage] = useState({ results: [], total: 0, facets: {}, notices: [], next: null, tools: [] })
  const [toolsKey, setToolsKey] = useState(0)
  const [searching, setSearching] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [detailError, setDetailError] = useState('')
  const [engine, setEngine] = useState('godot')
  const [sheet, setSheet] = useState(null)
  const [toast, setToast] = useState('')
  const [freesound, setFreesound] = useState(null) // connection state of the live sound source
  const [playing, setPlaying] = useState(null) // { id, state: 'loading' | 'playing' }
  const navRef = useRef(null)
  const readySent = useRef(false)
  const searchAbort = useRef(null)
  const scrollRef = useRef(null)
  const placeholder = useMemo(() => EXAMPLES[Math.floor(Math.random() * EXAMPLES.length)], [])

  // Library overview (counts, sources); also tells us whether the service runs here.
  useEffect(() => {
    let live = true
    api.overview().then((data) => {
      if (!live) return
      setOverview(data)
      setService('ready')
      if (!readySent.current) {
        readySent.current = true
        signal('app_ready', { item_count: data.total || 0 })
      }
    }).catch((err) => {
      if (!live) return
      setService('unavailable')
      setServiceError(err.message)
      signal('error', { source: 'overview', message: err.message })
    })
    return () => { live = false }
  }, [api])

  const refreshSources = useCallback(() => {
    api.sources().then((data) => setFreesound(data.freesound)).catch(() => {})
  }, [api])
  useEffect(() => {
    if (service === 'ready') refreshSources()
  }, [service, refreshSources])

  // Inline sound previews from the grid (one at a time).
  const playCard = useCallback(async (card) => {
    if (playing?.id === card.id) {
      stopPreview()
      setPlaying(null)
      return
    }
    setPlaying({ id: card.id, state: 'loading' })
    try {
      await playPreview(card.preview_small || card.preview_url, tokenRef, () =>
        setPlaying((current) => (current?.id === card.id ? null : current)))
      setPlaying((current) => (current?.id === card.id ? { id: card.id, state: 'playing' } : current))
    } catch (err) {
      setPlaying(null)
      setToast('That preview could not play')
      signal('error', { source: 'preview', message: err.message })
    }
  }, [playing])
  useEffect(() => () => stopPreview(), [])

  // Remember the preferred engine for import notes on this installation.
  useEffect(() => {
    window.mobius?.storage?.get('prefs.json').then((prefs) => {
      if (prefs?.engine) setEngine(prefs.engine)
    }).catch(() => {})
  }, [])
  const chooseEngine = useCallback((value) => {
    setEngine(value)
    window.mobius?.storage?.set('prefs.json', { engine: value }).catch(() => {})
  }, [])

  // Debounce typing into the submitted query.
  useEffect(() => {
    const timer = setTimeout(() => setQuery(input.trim()), 260)
    return () => clearTimeout(timer)
  }, [input])

  const runSearch = useCallback(async (offset = 0) => {
    searchAbort.current?.abort()
    if (type === 'tools') { setSearching(false); return } // the directory lists itself
    const controller = new AbortController()
    searchAbort.current = controller
    if (offset === 0) setSearching(true)
    else setLoadingMore(true)
    setSearchError('')
    try {
      const data = await api.search({ q: query, type, license, sort, limit: PAGE, offset }, controller.signal)
      setPage((prev) => ({
        results: offset === 0 ? data.results : [...prev.results, ...data.results],
        total: data.total, facets: data.facets || {}, notices: data.notices || [], next: data.next_offset,
        interpreted: data.interpreted, tools: offset === 0 ? (data.tools || []) : prev.tools,
      }))
      if (offset === 0 && scrollRef.current) scrollRef.current.scrollTop = 0
    } catch (err) {
      if (err?.name === 'AbortError') return
      setSearchError(err.message)
      signal('error', { source: 'search', message: err.message })
    } finally {
      if (searchAbort.current === controller) {
        setSearching(false)
        setLoadingMore(false)
      }
    }
  }, [api, query, type, license, sort])

  useEffect(() => {
    if (service === 'ready') runSearch(0)
  }, [service, runSearch])

  // Asset detail, with a host back entry so Back / swipe closes it.
  const wantedRef = useRef(null)
  const pendingTimer = useRef(null)
  // Entries whose source page is still being read (OpenGameArt) refresh quietly until their files are known.
  const refreshPending = useCallback((id, tries) => {
    clearTimeout(pendingTimer.current)
    if (tries <= 0) return
    pendingTimer.current = setTimeout(async () => {
      if (wantedRef.current !== id) return
      try {
        const data = await api.asset(id)
        if (wantedRef.current !== id) return
        setDetail(data)
        if (data.details_pending) refreshPending(id, tries - 1)
      } catch { /* keep what is shown; the next open retries */ }
    }, PENDING_RETRY_MS)
  }, [api])
  useEffect(() => () => clearTimeout(pendingTimer.current), [])

  const loadDetail = useCallback(async (id) => {
    wantedRef.current = id
    clearTimeout(pendingTimer.current)
    setDetail(null)
    setDetailError('')
    try {
      const data = await api.asset(id)
      if (wantedRef.current !== id) return // a newer asset was opened meanwhile
      setDetail(data)
      if (data.details_pending) refreshPending(id, PENDING_TRIES)
      signal('asset_opened', { type: data.type })
    } catch (err) {
      if (wantedRef.current !== id) return
      setDetailError(err.message)
      signal('error', { source: 'asset', message: err.message })
    }
  }, [api, refreshPending])

  const openAsset = useCallback((id) => {
    setSelectedId(id)
    loadDetail(id)
    if (!navRef.current && window.mobius?.nav?.open) {
      let handle = null
      handle = window.mobius.nav.open('asset-detail', {
        onBack: () => { navRef.current = null; setSelectedId(null); setDetail(null) },
        onForward: () => { navRef.current = handle },
      })
      navRef.current = handle
      handle.outcome?.then(({ status }) => {
        if (status !== 'owned' && navRef.current === handle) navRef.current = null
      }).catch(() => {})
    }
  }, [loadDetail])

  const closeAsset = useCallback(() => {
    navRef.current?.close()
    navRef.current = null
    wantedRef.current = null
    setSelectedId(null)
    setDetail(null)
  }, [])

  // Shell deep links: chat activity cards open `asset:<id>`; `search:<words>` runs a search.
  useEffect(() => {
    function onMessage(event) {
      if (event.source !== window.parent || event.data?.type !== 'moebius:app-intent') return
      const intent = typeof event.data.intent === 'string' ? event.data.intent : ''
      if (intent.startsWith('asset:')) openAsset(intent.slice(6))
      else if (intent.startsWith('tool:')) openAsset(intent)
      else if (intent.startsWith('search:')) { setInput(intent.slice(7)); setType('') }
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [openAsset])

  const copy = useCallback(async (text, message) => {
    const ok = await window.mobius?.clipboard?.writeText(text)
    setToast(ok ? message : 'Copy failed — select the text and press Ctrl+C')
  }, [])
  useEffect(() => {
    if (!toast) return undefined
    const timer = setTimeout(() => setToast(''), 1800)
    return () => clearTimeout(timer)
  }, [toast])

  const searchTag = useCallback((tag) => {
    setInput(tag)
    setType('')
  }, [])

  const typeCounts = page.facets?.type || {}
  const allCount = Object.values(typeCounts).reduce((sum, n) => sum + n, 0)
  const total = overview?.total || 0

  return (
    <div className="ac-root">
      <style>{CSS}</style>
      <header className="ac-header">
        <div className="ac-brand">
          <span className="ac-mark" aria-hidden="true"><span /><span /><span /><span /></span>
          <div style={{ minWidth: 0 }}>
            <h1 className="ac-title">Asset Commons</h1>
            <span className="ac-subtitle">
              {service === 'ready'
                ? (freesound?.connected && freesound.cc0_sounds
                  ? `${total.toLocaleString()} free assets + ${freesound.cc0_sounds.toLocaleString()} CC0 sounds via Freesound`
                  : `${total.toLocaleString()} free assets · shared resources for agents and humans`)
                : 'Shared resources for agents and humans'}
            </span>
          </div>
        </div>
        <div className="ac-header-right">
          <button type="button" className="ac-btn" onClick={() => setSheet('sources')} disabled={service !== 'ready'}>
            <Globe aria-hidden="true" /><span className="ac-btn-label">Sources</span>
          </button>
          <button type="button" className="ac-btn" onClick={() => setSheet('agents')} disabled={service !== 'ready'}>
            <Robot aria-hidden="true" /><span className="ac-btn-label">For agents</span>
          </button>
        </div>
      </header>

      {service === 'unavailable' ? (
        <EmptyState icon={<InfoCircle />} title="The library isn’t running here">
          Asset Commons keeps its catalogue in its own small server. Install the app on this Möbius to browse it
          and give your agents the asset tools. {serviceError ? `(${serviceError})` : ''}
        </EmptyState>
      ) : (
        <>
          <div className="ac-toolbar">
            <label className="ac-search">
              <Search aria-hidden="true" />
              <input
                type="search" value={input} onChange={(event) => setInput(event.target.value)}
                placeholder={`Search free assets — try “${placeholder}”`} aria-label="Search assets"
                autoComplete="off" spellCheck="false"
              />
              {input && (
                <button type="button" className="ac-btn is-ghost ac-icon-btn" onClick={() => setInput('')} aria-label="Clear search">
                  <XCrossed />
                </button>
              )}
            </label>
            <div className="ac-seg" role="tablist" aria-label="Asset type">
              <button type="button" role="tab" aria-selected={type === ''} className={`ac-seg-btn${type === '' ? ' is-active' : ''}`}
                onClick={() => setType('')}>All <span className="ac-count">{allCount.toLocaleString()}</span></button>
              {TYPE_ORDER.map((key) => (
                <button key={key} type="button" role="tab" aria-selected={type === key}
                  className={`ac-seg-btn${type === key ? ' is-active' : ''}`} onClick={() => setType(key)}>
                  <span className="ac-dot" style={{ background: typeColor(key) }} />
                  {TYPE_LABELS[key]} <span className="ac-count">{(typeCounts[key] || 0).toLocaleString()}</span>
                </button>
              ))}
              <button type="button" role="tab" aria-selected={type === 'tools'}
                className={`ac-seg-btn is-tools${type === 'tools' ? ' is-active' : ''}`} onClick={() => setType('tools')}>
                <Tools aria-hidden="true" width={15} height={15} />Tools <span className="ac-count">{overview?.tools ?? ''}</span>
              </button>
            </div>
          </div>

          <div className="ac-body">
            <div className="ac-scroll" ref={scrollRef}>
              {type === 'tools' ? (
                <ToolsView api={api} query={query} onOpen={openAsset} refreshKey={toolsKey}
                  onAdded={(result) => { setToast(result.outcome === 'added' ? 'Added to the directory' : 'Already listed'); setOverview((o) => o && ({ ...o, tools: (o.tools || 0) + (result.outcome === 'added' ? 1 : 0) })) }} />
              ) : service === 'loading' || (searching && !page.results.length) ? (
                <Skeletons />
              ) : searchError ? (
                <EmptyState icon={<InfoCircle />} title="Search didn’t go through"
                  action={<button type="button" className="ac-btn" onClick={() => runSearch(0)}>Try again</button>}>
                  {searchError}
                </EmptyState>
              ) : (
                <>
                  <div className="ac-summary">
                    <span aria-live="polite"><strong>{page.total.toLocaleString()}</strong> {page.total === 1 ? 'asset' : 'assets'}
                      {query ? <> for “{query}”</> : type ? <> in {TYPE_LABELS[type]}</> : ''}
                      {searching ? ' · updating…' : ''}</span>
                    <span className="ac-summary-controls">
                      <select className="ac-select is-compact" value={license} onChange={(event) => setLicense(event.target.value)} aria-label="Licence">
                        {LICENSES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                      </select>
                      <select className="ac-select is-compact" value={sort} onChange={(event) => setSort(event.target.value)} aria-label="Sort">
                        {SORTS.filter(([value]) => query || value !== 'popular').map(([value, label]) => (
                          <option key={value} value={value}>{value === '' && !query ? 'Most popular' : label}</option>
                        ))}
                      </select>
                    </span>
                  </div>
                  {understood(page.interpreted, type, license) && (
                    <div className="ac-understood"><span>Understood as</span> {understood(page.interpreted, type, license)}</div>
                  )}
                  {page.notices.filter((notice) => !(type === 'sound' && !page.results.length && notice.startsWith('Connect Freesound'))
                    && !(page.tools?.length && notice.startsWith('Tools that can make this'))).map((notice) => (
                    <div key={notice} className="ac-notice"><InfoCircle aria-hidden="true" /><span>{notice}</span></div>
                  ))}
                  {(!page.results.length || page.interpreted?.intent === 'make') && (
                    <ToolStrip tools={page.tools} onOpen={openAsset} prominent />
                  )}
                  {page.results.length ? (
                    <>
                      <AssetGrid results={page.results} selectedId={selectedId} onOpen={openAsset} tokenRef={tokenRef}
                        playing={playing} onPlay={playCard} />
                      {page.interpreted?.intent !== 'make' && <div style={{ marginTop: 16 }}><ToolStrip tools={page.tools} onOpen={openAsset} /></div>}
                      {page.next != null && (
                        <div className="ac-more">
                          <button type="button" className="ac-btn" onClick={() => runSearch(page.next)} disabled={loadingMore}>
                            {loadingMore ? 'Loading…' : `Show more (${(page.total - page.results.length).toLocaleString()} left)`}
                          </button>
                        </div>
                      )}
                    </>
                  ) : (
                    type === 'sound' && freesound && !freesound.connected ? (
                      <EmptyState icon={<Globe />} title="Connect Freesound for sounds"
                        action={<div className="ac-cta-row"><button type="button" className="ac-btn is-primary" onClick={() => setSheet('sources')}>Connect Freesound</button></div>}>
                        Freesound has hundreds of thousands of CC0 sound effects, ambiences and loops. Connect a free
                        Freesound API key and Asset Commons searches it live for you and every agent.
                      </EmptyState>
                    ) : (
                      <EmptyState icon={<Search />} title="Nothing matches">
                        {type === 'music'
                          ? 'Try a mood or genre — “calm”, “battle”, “chiptune”, “orchestral” — or fewer words.'
                          : 'Try fewer words, another type, or “Any free licence”.'}
                      </EmptyState>
                    )
                  )}
                </>
              )}
            </div>
            {selectedId && selectedId.startsWith('tool:') && (
              <ToolDetail api={api} tool={detail && detail.id === selectedId ? detail : null}
                loading={!detail || detail.id !== selectedId} error={detailError} onClose={closeAsset}
                onChanged={() => { loadDetail(selectedId); setToolsKey((k) => k + 1) }} onCopy={copy} />
            )}
            {selectedId && !selectedId.startsWith('tool:') && (
              <AssetDetail
                api={api}
                onChanged={() => loadDetail(selectedId)}
                asset={detail && detail.id === selectedId ? detail : null}
                loading={!detail || detail.id !== selectedId}
                error={detailError}
                onClose={closeAsset}
                onOpen={openAsset}
                onTag={searchTag}
                onCopy={copy}
                onRetry={() => loadDetail(selectedId)}
                tokenRef={tokenRef}
                engine={engine}
                onEngine={chooseEngine}
              />
            )}
          </div>
        </>
      )}
      {sheet === 'agents' && (
        <AgentSheet appId={appId} onClose={() => setSheet(null)} onCopy={copy} onOpenSources={() => setSheet('sources')} />
      )}
      {sheet === 'sources' && (
        <SourcesSheet api={api} overview={overview} onClose={() => setSheet(null)}
          onChanged={() => { refreshSources(); runSearch(0) }} />
      )}
      {toast && <div className="ac-toast" role="status">{toast}</div>}
    </div>
  )
}
