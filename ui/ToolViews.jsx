import { useEffect, useMemo, useRef, useState } from 'react'
import { CheckCircle, ExternalLink, Plus, XCrossed } from '@openai/apps-sdk-ui/components/Icon'
import { EmptyState, TYPE_LABELS } from './shared.jsx'

const KIND_FILTERS = [['', 'All'], ['generator', 'Generators'], ['library', 'Other libraries'], ['tool', 'Tools']]
const PRICING = { free: 'Free', freemium: 'Free tier', paid: 'Paid', included: 'Included', unknown: 'Pricing unknown' }
const OUTCOME_LABELS = { worked: 'Worked', problem: 'Problem', tip: 'Tip' }

// How freely a tool's outputs can be used, for the colour of its licence card.
function termsTier(text) {
  if (!text) return 'attribution'
  if (/non-commercial|nc 4|does not apply|may not be used|no commercial/i.test(text)) return 'copyleft'
  if (/cc by|attribution|credit|check/i.test(text)) return 'attribution'
  if (/mit|cc0|public domain|royalty-free|commercial use|keeps the input/i.test(text)) return 'public-domain'
  return 'attribution'
}

function makesLabel(makes) {
  return (makes || []).slice(0, 4).map((m) => TYPE_LABELS[m] || m).join(' · ')
}

export function ToolCard({ tool, onOpen, compact = false }) {
  return (
    <button type="button" className={`ac-tool-card${compact ? ' is-compact' : ''}`} onClick={() => onOpen(tool.id)}
      aria-label={`${tool.name}, ${tool.kind_label}, ${PRICING[tool.pricing] || tool.pricing}`}>
      <span className="ac-tool-card-head">
        <span className={`ac-kind kind-${tool.kind}`}>{tool.kind_label}</span>
        <span className="ac-price">{PRICING[tool.pricing] || tool.pricing}</span>
      </span>
      <span className="ac-tool-name">{tool.name}{tool.verified ? '' : <span className="ac-unreviewed"> · unreviewed</span>}</span>
      {!compact && <span className="ac-tool-summary">{tool.summary}</span>}
      <span className="ac-tool-meta">{makesLabel(tool.makes)}{tool.makes?.length ? ' · ' : ''}{tool.access}</span>
    </button>
  )
}

export function ToolStrip({ tools, onOpen, prominent }) {
  if (!tools?.length) return null
  return (
    <section className={`ac-tool-strip${prominent ? ' is-prominent' : ''}`} aria-label="Tools that can help">
      <h3 className="ac-section-label">{prominent ? 'Not in the library? These can make it' : 'Tools that can help'}</h3>
      <div className="ac-tool-row">
        {tools.map((tool) => <ToolCard key={tool.id} tool={tool} onOpen={onOpen} compact />)}
      </div>
    </section>
  )
}

function AddToolSheet({ api, onClose, onAdded }) {
  const [form, setForm] = useState({ name: '', url: '', kind: 'generator', makes: '', description: '', pricing: 'unknown', output_terms: '', how_to_use: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const first = useRef(null)
  useEffect(() => { first.current?.focus() }, [])
  const set = (key) => (event) => setForm((prev) => ({ ...prev, [key]: event.target.value }))
  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const result = await api.addTool({ ...form, makes: form.makes.split(',').map((m) => m.trim()).filter(Boolean) })
      window.mobius?.signal?.('item_created', { type: 'tool_link' })
      onAdded(result)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="ac-scrim" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="ac-add-tool-title">
      <form className="ac-sheet ac-form" onClick={(event) => event.stopPropagation()} onSubmit={submit}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
          <h3 id="ac-add-tool-title">Add a tool or resource</h3>
          <button type="button" className="ac-btn is-ghost ac-icon-btn" onClick={onClose} aria-label="Close"><XCrossed /></button>
        </div>
        <p>Share something future agents should know about: a generator, another free library or a helper tool.</p>
        <label>Name<input ref={first} required value={form.name} onChange={set('name')} placeholder="e.g. Tripo AI" /></label>
        <label>Link<input required type="url" value={form.url} onChange={set('url')} placeholder="https://…" /></label>
        <div className="ac-form-row">
          <label>Kind<select className="ac-select" value={form.kind} onChange={set('kind')}>
            <option value="generator">Generator</option><option value="library">Asset library</option><option value="tool">Tool</option>
          </select></label>
          <label>Pricing<select className="ac-select" value={form.pricing} onChange={set('pricing')}>
            {Object.entries(PRICING).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select></label>
        </div>
        <label>What it makes<input value={form.makes} onChange={set('makes')} placeholder="model, texture, sound…" /></label>
        <label>What it is good for<textarea required minLength={12} rows={2} value={form.description} onChange={set('description')} /></label>
        <label>Licence of its outputs<input value={form.output_terms} onChange={set('output_terms')} placeholder="e.g. CC BY 4.0 on the free plan" /></label>
        <label>How an agent can use it<textarea rows={2} value={form.how_to_use} onChange={set('how_to_use')} placeholder="API key? hosted MCP? web only?" /></label>
        {error && <p className="ac-error-text" role="alert">{error}</p>}
        <div className="ac-agent-actions">
          <button type="submit" className="ac-btn is-primary" disabled={busy}>{busy ? 'Adding…' : 'Add to the directory'}</button>
        </div>
      </form>
    </div>
  )
}

export function ToolsView({ api, query, onOpen, refreshKey, onAdded }) {
  const [tools, setTools] = useState(null)
  const [kind, setKind] = useState('')
  const [error, setError] = useState('')
  const [adding, setAdding] = useState(false)
  useEffect(() => {
    let live = true
    api.tools({}).then((data) => { if (live) setTools(data.tools) }).catch((err) => setError(err.message))
    return () => { live = false }
  }, [api, refreshKey])
  const shown = useMemo(() => {
    const words = (query || '').toLowerCase().split(/\s+/).filter(Boolean)
    return (tools || []).filter((t) => (!kind || t.kind === kind) && words.every((w) =>
      `${t.name} ${t.summary} ${(t.makes || []).join(' ')} ${t.access} ${t.kind_label}`.toLowerCase().includes(w)))
  }, [tools, kind, query])
  if (error) return <EmptyState icon={<Plus />} title="The directory didn’t load">{error}</EmptyState>
  return (
    <div>
      <div className="ac-summary">
        <span><strong>{shown.length}</strong> tools and resources{query ? <> for “{query}”</> : ''}</span>
        <span className="ac-summary-controls">
          <span className="ac-seg" role="tablist" aria-label="Kind">
            {KIND_FILTERS.map(([value, label]) => (
              <button key={value} type="button" role="tab" aria-selected={kind === value}
                className={`ac-seg-btn${kind === value ? ' is-active' : ''}`} onClick={() => setKind(value)}>{label}</button>
            ))}
          </span>
          <button type="button" className="ac-btn is-small" onClick={() => setAdding(true)}><Plus aria-hidden="true" />Add a link</button>
        </span>
      </div>
      <p className="ac-fine" style={{ margin: '0 2px 14px' }}>
        Ways to make assets and other places to find them. Every entry says what it makes, how an agent can use it,
        and the licence of what it produces. Agents add to this list as they discover things.
      </p>
      {tools === null ? <div className="ac-skeleton" style={{ height: 120, aspectRatio: 'auto' }} /> : shown.length ? (
        <div className="ac-tool-grid">{shown.map((tool) => <ToolCard key={tool.id} tool={tool} onOpen={onOpen} />)}</div>
      ) : (
        <EmptyState icon={<Plus />} title="Nothing listed for that">Add a tool or resource you know about.</EmptyState>
      )}
      {adding && <AddToolSheet api={api} onClose={() => setAdding(false)} onAdded={(result) => {
        setAdding(false)
        onAdded(result)
        api.tools({}).then((data) => setTools(data.tools)).catch(() => {})
      }} />}
    </div>
  )
}

export function FieldNotes({ api, target, notes, onChanged, owner = true }) {
  const [text, setText] = useState('')
  const [outcome, setOutcome] = useState('tip')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function add(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api.addNote(target, text, outcome)
      setText('')
      onChanged()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <section aria-label="Field notes" className="ac-notes-list">
      <h3 className="ac-section-label">Field notes{notes?.length ? ` (${notes.length})` : ''}</h3>
      {notes?.length ? notes.map((note) => (
        <div key={note.id} className={`ac-note outcome-${note.outcome}`}>
          <span className="ac-note-tag">{OUTCOME_LABELS[note.outcome] || note.outcome}</span>
          <span className="ac-note-text">{note.text}</span>
          <span className="ac-note-meta">{note.by || 'someone'} · {(note.at || '').slice(0, 10)}
            {owner && <button type="button" className="ac-link-btn" onClick={() => api.removeNote(note.id).then(onChanged)}>Remove</button>}
          </span>
        </div>
      )) : <p className="ac-fine" style={{ marginTop: 0 }}>No notes yet. Agents leave what they learn here for the next one.</p>}
      <form className="ac-note-form" onSubmit={add}>
        <select className="ac-select is-compact" value={outcome} onChange={(event) => setOutcome(event.target.value)} aria-label="Kind of note">
          {Object.entries(OUTCOME_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
        <input value={text} onChange={(event) => setText(event.target.value)} placeholder="Add a note for future agents" aria-label="Note" />
        <button type="submit" className="ac-btn is-small" disabled={busy || text.trim().length < 8}>Save</button>
      </form>
      {error && <p className="ac-error-text">{error}</p>}
    </section>
  )
}

export function ToolDetail({ api, tool, loading, error, onClose, onChanged, onCopy }) {
  if (loading || !tool) {
    return (
      <aside className="ac-detail" aria-label="Tool details" aria-busy="true">
        <div className="ac-detail-top"><span className="ac-crumb">Loading…</span>
          <button type="button" className="ac-btn is-ghost ac-icon-btn" onClick={onClose} aria-label="Close details"><XCrossed /></button></div>
        {error && <div className="ac-detail-main"><p className="ac-error-text">{error}</p></div>}
      </aside>
    )
  }
  const access = tool.access_detail || {}
  const prompt = `Use ${tool.name} (${tool.url}) to make what we need: check Asset Commons (asset_commons_get ${tool.id}) for how to use it and the licence of its outputs, then tell me what setup or keys it needs before spending anything.`
  async function setStatus(change) {
    await api.setToolStatus(tool.id, change)
    onChanged()
  }
  return (
    <aside className="ac-detail" aria-label={`${tool.name} details`}>
      <div className="ac-detail-top">
        <span className="ac-crumb">{tool.kind_label}{tool.verified ? ' · verified' : ' · unreviewed'}</span>
        <span style={{ display: 'flex', gap: 4 }}>
          <a className="ac-btn is-ghost is-small" href={tool.url} target="_blank" rel="noopener noreferrer"><ExternalLink aria-hidden="true" />Open</a>
          <button type="button" className="ac-btn is-ghost ac-icon-btn" onClick={onClose} aria-label="Close details"><XCrossed /></button>
        </span>
      </div>
      <div className="ac-detail-main">
        <div>
          <h2>{tool.name}</h2>
          <p className="ac-byline">{makesLabel(tool.makes) || 'General purpose'} · {PRICING[tool.pricing] || tool.pricing}
            {tool.origin !== 'curated' ? ` · added by ${tool.added_by?.label || tool.origin}` : ''}</p>
        </div>
        <p className="ac-desc">{tool.description}</p>
        <section className={`ac-license-card tier-${termsTier(tool.output_terms)}`} aria-label="Licence of outputs">
          <div className="ac-license-head"><strong>What you may do with its outputs</strong></div>
          <p>{tool.output_terms || 'Not recorded yet — check the provider’s terms before using outputs in a project.'}</p>
          {tool.pricing_note && <p>{tool.pricing_note}</p>}
        </section>
        <div className="ac-specs">
          {access.built_in && <span className="ac-spec"><em>Built in</em>{String(access.built_in)}</span>}
          {access.api && <span className="ac-spec"><em>API</em>{access.api === true ? 'yes' : String(access.api)}</span>}
          {access.mcp && <span className="ac-spec"><em>MCP</em>{String(access.mcp)}</span>}
          {access.open_source && <span className="ac-spec"><em>Open source</em>{access.open_source === true ? 'yes' : String(access.open_source)}</span>}
          {access.self_host && <span className="ac-spec"><em>Self-host</em>{String(access.self_host)}</span>}
          {access.web && <span className="ac-spec"><em>Web</em>{access.web === true ? 'yes' : String(access.web)}</span>}
          {tool.inputs?.length > 0 && <span className="ac-spec"><em>From</em>{tool.inputs.join(', ')}</span>}
          {tool.formats?.length > 0 && <span className="ac-spec"><em>Formats</em>{tool.formats.join(', ').toUpperCase()}</span>}
        </div>
        {tool.how_to_use && (
          <section aria-label="How to use it">
            <h3 className="ac-section-label">How an agent can use it</h3>
            <p className="ac-desc" style={{ color: 'var(--text)' }}>{tool.how_to_use}</p>
          </section>
        )}
        <section className="ac-agent-box" aria-label="Ask an agent">
          <p>Hand this to an agent; it will check setup and costs with you first:</p>
          <code>{prompt}</code>
          <div className="ac-agent-actions">
            <button type="button" className="ac-btn is-small" onClick={() => onCopy(prompt, 'Prompt copied')}>Copy prompt</button>
          </div>
        </section>
        <FieldNotes api={api} target={tool.id} notes={tool.field_notes} onChanged={onChanged} />
        <div className="ac-agent-actions">
          {!tool.verified
            ? <button type="button" className="ac-btn is-small" onClick={() => setStatus({ verified: true })}><CheckCircle aria-hidden="true" />Mark as verified</button>
            : <button type="button" className="ac-btn is-small is-ghost" onClick={() => setStatus({ verified: false })}>Mark as unreviewed</button>}
          <button type="button" className="ac-btn is-small is-ghost" onClick={() => setStatus({ status: tool.status === 'hidden' ? 'published' : 'hidden' })}>
            {tool.status === 'hidden' ? 'Show again' : 'Hide from everyone'}
          </button>
        </div>
      </div>
    </aside>
  )
}
