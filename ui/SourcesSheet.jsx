import { useCallback, useEffect, useRef, useState } from 'react'
import { CheckCircle, ExternalLink, Key, XCrossed } from '@openai/apps-sdk-ui/components/Icon'

const STEPS = [
  ['Sign in or create a free account on Freesound.', 'https://freesound.org/home/register/', 'freesound.org'],
  ['Open the API credentials page and create a key (any name, e.g. “Asset Commons”).', 'https://freesound.org/apiv2/apply', 'freesound.org/apiv2/apply'],
  ['Copy the long “Client secret / Api key” value and paste it below.', null, null],
]

function FreesoundPanel({ api, state, onState, onChanged }) {
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const connected = state?.state === 'connected' || state?.state === 'throttled' || state?.state === 'unreachable'

  async function save(event) {
    event.preventDefault()
    const key = value.trim()
    if (!key) return
    setBusy('saving')
    setError('')
    try {
      await api.saveFreesoundKey(key)
      setValue('') // never keep the key around in the page
      await api.forgetFreesound()
      const result = await api.checkFreesound()
      onState(result.freesound)
      if (result.freesound.state === 'rejected') {
        setError('Freesound did not accept that key. Check that you copied the “Client secret / Api key” value, not the client id.')
      } else {
        window.mobius?.signal?.('item_created', { type: 'source_key' })
        onChanged()
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy('')
    }
  }

  async function disconnect() {
    setBusy('removing')
    setError('')
    try {
      await api.removeFreesoundKey()
      await api.forgetFreesound()
      const result = await api.sources()
      onState(result.freesound)
      window.mobius?.signal?.('item_deleted', { type: 'source_key' })
      onChanged()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy('')
    }
  }

  return (
    <section className="ac-source-card" aria-labelledby="ac-freesound-title">
      <div className="ac-source-card-head">
        <div>
          <h4 id="ac-freesound-title">Freesound</h4>
          <p>CC0 sound effects, ambience and music, searched live.</p>
        </div>
        <span className={`ac-pill${connected ? ' is-live' : ''}`}>
          {state ? (connected ? 'Connected' : state.state === 'rejected' ? 'Key rejected' : 'Not connected') : 'Checking…'}
        </span>
      </div>
      {connected ? (
        <>
          <p className="ac-source-status"><CheckCircle aria-hidden="true" />{state.message}</p>
          <p className="ac-fine">
            Your key is stored encrypted by Möbius. Only Asset Commons’ own server reads it, to search Freesound;
            it never appears in chats or reaches the AI. Searches are cached for an hour, and only sounds someone
            downloads are kept, as Freesound’s terms ask.
          </p>
          <div className="ac-agent-actions">
            <button type="button" className="ac-btn is-small" onClick={disconnect} disabled={!!busy}>
              {busy === 'removing' ? 'Disconnecting…' : 'Disconnect'}
            </button>
          </div>
        </>
      ) : (
        <>
          <ol className="ac-steps">
            {STEPS.map(([text, href, label]) => (
              <li key={text}>{text}{href && (
                <> <a href={href} target="_blank" rel="noopener noreferrer">{label}<ExternalLink aria-hidden="true" /></a></>
              )}</li>
            ))}
          </ol>
          <form className="ac-key-form" onSubmit={save}>
            <label className="ac-search">
              <Key aria-hidden="true" />
              <input type="password" value={value} onChange={(event) => setValue(event.target.value)}
                placeholder="Paste your Freesound API key" aria-label="Freesound API key"
                autoComplete="off" spellCheck="false" disabled={!!busy} />
            </label>
            <button type="submit" className="ac-btn is-primary" disabled={!value.trim() || !!busy}>
              {busy === 'saving' ? 'Checking…' : 'Connect'}
            </button>
          </form>
          {state?.state === 'rejected' && (
            <div className="ac-agent-actions">
              {!error && <p className="ac-error-text" style={{ margin: 0, flex: 1 }}>{state.message}</p>}
              <button type="button" className="ac-btn is-small" onClick={disconnect} disabled={!!busy}>
                {busy === 'removing' ? 'Removing…' : 'Remove saved key'}
              </button>
            </div>
          )}
          <p className="ac-fine">
            The key goes straight into Möbius’s encrypted storage for this app; it never passes through a chat or
            the AI. You can disconnect at any time.
          </p>
        </>
      )}
      {error && <p className="ac-error-text" role="alert">{error}</p>}
    </section>
  )
}

export default function SourcesSheet({ api, overview, onClose, onChanged }) {
  const closeRef = useRef(null)
  const [data, setData] = useState(null)
  const [loadError, setLoadError] = useState('')
  const load = useCallback(() => {
    api.sources().then(setData).catch((err) => setLoadError(err.message))
  }, [api])
  useEffect(() => {
    closeRef.current?.focus()
    load()
    const onKey = (event) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [load, onClose])
  const others = (data?.sources || overview?.source_info || []).filter((source) => source.id !== 'freesound')
  return (
    <div className="ac-scrim" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="ac-sources-title">
      <div className="ac-sheet" onClick={(event) => event.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
          <h3 id="ac-sources-title">Sources</h3>
          <button ref={closeRef} type="button" className="ac-btn is-ghost ac-icon-btn" onClick={onClose} aria-label="Close"><XCrossed /></button>
        </div>
        <p>Where Asset Commons finds its assets. Every source here publishes free, openly licensed work, CC0 first.</p>
        <FreesoundPanel api={api} state={data?.freesound} onState={(freesound) => setData((prev) => ({ ...(prev || {}), freesound }))}
          onChanged={onChanged} />
        {loadError && <p className="ac-error-text">{loadError}</p>}
        <h3 className="ac-section-label" style={{ marginTop: 18 }}>Library sources</h3>
        <div>
          {others.map((source) => {
            const reading = source.reading?.waiting ? source.reading : null
            return (
              <div key={source.id} className="ac-source-row">
                <strong>{source.name}</strong>
                <span>{source.status === 'indexed'
                  ? `${(source.assets ?? overview?.by_source?.[source.id] ?? 0).toLocaleString()} assets · ${source.credit}`
                  : source.note}
                {reading && (
                  <em className="ac-source-progress">
                    Reading entry pages in the background: {reading.read.toLocaleString()} done,
                    {' '}{reading.waiting.toLocaleString()} to go{reading.hours_left >= 1 ? ` (about ${Math.round(reading.hours_left)} h)` : ''}.
                    {' '}Everything is searchable by title already; opening an entry reads it first.
                  </em>
                )}
                </span>
                <span className={`ac-pill${source.status === 'indexed' ? ' is-live' : ''}`}>
                  {reading ? 'Reading' : source.status === 'indexed' ? 'Indexed' : 'Planned'}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
