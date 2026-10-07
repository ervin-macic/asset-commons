import { useEffect, useRef } from 'react'
import { Copy, XCrossed } from '@openai/apps-sdk-ui/components/Icon'

const TOOLS = [
  ['asset_commons_search', 'Natural-language search with filters: “mossy rock texture, cc0, 2k”, “8-bit battle music”, “wooden chair under 10k tris”. Suggests tools when the library lacks something.'],
  ['asset_commons_get', 'Full details for one asset or tool: licence and credit line, every download with sizes, what is inside a pack, engine import notes.'],
  ['asset_commons_download', 'Puts an asset, or single items from a pack, in a project folder with provenance (asset-commons.json) and a licence file.'],
  ['asset_commons_credits', 'Builds CREDITS.md for a project from what was downloaded, grouped by what each licence asks.'],
  ['asset_commons_note', 'Leaves a field note on an asset or tool for the next agent: what worked, what went wrong, a tip.'],
  ['asset_commons_add_resource', 'Adds a useful generator, library or tool to the directory, with its pricing and the licence of its outputs.'],
]
const EXAMPLE = 'Find a CC0 mossy rock texture in Asset Commons and use it on the ground in my Godot project.'

export default function AgentSheet({ appId, onClose, onCopy, onOpenSources }) {
  const closeRef = useRef(null)
  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (event) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="ac-scrim" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="ac-agents-title">
      <div className="ac-sheet" onClick={(event) => event.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
          <div>
            <h3 id="ac-agents-title">Shared with every agent</h3>
          </div>
          <button ref={closeRef} type="button" className="ac-btn is-ghost ac-icon-btn" onClick={onClose} aria-label="Close"><XCrossed /></button>
        </div>
        <p>
          Claude, Codex and their helpers on this Möbius can search and pull from this library directly. A short
          note in every agent’s instructions tells them to check here before making textures, models, skies or
          sounds from scratch, and to keep the credits.
        </p>
        <div className="ac-tool-list">
          {TOOLS.map(([name, text]) => (
            <div key={name} className="ac-tool"><code>{name}</code><p>{text}</p></div>
          ))}
        </div>
        <h3 className="ac-section-label">Try it in any chat</h3>
        <div className="ac-agent-box" style={{ marginBottom: 18 }}>
          <code>{EXAMPLE}</code>
          <div className="ac-agent-actions">
            <button type="button" className="ac-btn is-small" onClick={() => onCopy(EXAMPLE, 'Prompt copied')}><Copy aria-hidden="true" />Copy prompt</button>
          </div>
        </div>
        <div className="ac-agent-actions" style={{ marginBottom: 6 }}>
          <button type="button" className="ac-btn is-small" onClick={onOpenSources}>Sources and Freesound connection</button>
        </div>
        <p style={{ marginTop: 16, fontSize: 12.5 }}>
          Scripts can use the same library over HTTP with owner credentials:
          {' '}<code style={{ fontFamily: 'var(--mono)' }}>GET /api/apps/{appId}/service/search?q=…</code>
        </p>
      </div>
    </div>
  )
}
