// Asset Commons stylesheet. Theme tokens come from the owner's Möbius theme;
// type hues are small identity accents (glyph badges), never large fills.
export const CSS = `
* { box-sizing: border-box; }
.ac-root {
  position: relative; display: flex; flex-direction: column; height: 100%; width: 100%;
  overflow: hidden; background: var(--bg); color: var(--text); font-family: var(--font);
  -webkit-font-smoothing: antialiased; font-size: 14px;
  --ac-texture: #d39a6a; --ac-model: #7cb0ff; --ac-hdri: #f2c14e; --ac-sound: #4fd1c5; --ac-animation: #f38bc8;
  --ac-sprite: #9ad66b; --ac-ui: #e7a8ff; --ac-music: #8f9cff;
  --ac-pd: var(--green, #10b981); --ac-by: #f5b544; --ac-sa: #fb923c; --ac-copyleft: #f87171;
}
.ac-root button, .ac-root input, .ac-root select { font-family: inherit; }
.ac-root :focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

/* Header */
.ac-header {
  flex: 0 0 auto; display: flex; align-items: center; justify-content: space-between; gap: 12px;
  min-height: 56px; padding: 10px 16px; padding-top: max(10px, env(safe-area-inset-top));
  background: var(--surface); border-bottom: 1px solid var(--border);
}
.ac-brand { display: flex; align-items: center; gap: 11px; min-width: 0; }
.ac-mark { flex: 0 0 auto; width: 32px; height: 32px; display: grid; grid-template-columns: 1fr 1fr; gap: 3px; }
.ac-mark span { border-radius: 4px; }
.ac-mark span:nth-child(1) { background: var(--ac-texture); }
.ac-mark span:nth-child(2) { background: var(--ac-model); border-radius: 50%; }
.ac-mark span:nth-child(3) { background: var(--ac-sound); }
.ac-mark span:nth-child(4) { background: var(--accent); border-radius: 4px 12px 4px 4px; }
.ac-title { margin: 0; font-size: 17px; font-weight: 750; letter-spacing: -0.015em; line-height: 1.15; }
.ac-subtitle { display: block; margin-top: 2px; font-size: 12px; color: var(--muted); white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; font-variant-numeric: tabular-nums; }
.ac-header-right { display: flex; gap: 8px; align-items: center; }

/* Buttons */
.ac-btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 7px; min-height: 40px;
  padding: 0 14px; border-radius: 10px; border: 1px solid var(--border); background: var(--surface-2);
  color: var(--text); font-size: 13px; font-weight: 650; cursor: pointer; white-space: nowrap;
  transition: background .15s, border-color .15s, color .15s;
}
.ac-btn:hover { border-color: color-mix(in srgb, var(--accent) 45%, var(--border)); }
.ac-btn.is-primary { background: var(--accent); border-color: var(--accent); color: var(--accent-fg); }
.ac-btn.is-primary:hover { background: var(--accent-hover, var(--accent)); }
.ac-btn.is-ghost { background: transparent; border-color: transparent; color: var(--muted); }
.ac-btn.is-ghost:hover { color: var(--text); background: var(--surface-2); }
.ac-btn:disabled { opacity: .5; cursor: not-allowed; }
.ac-btn.is-small { min-height: 32px; padding: 0 10px; font-size: 12px; border-radius: 8px; }
.ac-icon-btn { width: 40px; padding: 0; }
.ac-btn svg, .ac-chip svg, .ac-search svg { width: 17px; height: 17px; flex: 0 0 auto; }

/* Toolbar */
.ac-toolbar {
  flex: 0 0 auto; display: flex; flex-wrap: wrap; align-items: center; gap: 10px;
  padding: 12px 16px; border-bottom: 1px solid var(--border); background: var(--bg);
}
.ac-search {
  flex: 1 1 300px; min-width: 200px; display: flex; align-items: center; gap: 8px; height: 44px;
  padding: 0 6px 0 13px; border-radius: 12px; background: var(--surface); border: 1px solid var(--border);
  color: var(--muted); transition: border-color .15s, box-shadow .15s;
}
.ac-search:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim); color: var(--text); }
.ac-search input {
  flex: 1; min-width: 0; height: 100%; border: 0; outline: 0; background: transparent; color: var(--text);
  font-size: 15px;
}
.ac-search input::placeholder { color: var(--muted); }
.ac-search input:focus-visible { outline: none; }
.ac-search input::-webkit-search-cancel-button, .ac-search input::-webkit-search-decoration { -webkit-appearance: none; appearance: none; display: none; }
.ac-seg { display: inline-flex; gap: 2px; padding: 2px; border-radius: 11px; background: var(--surface);
  box-shadow: inset 0 0 0 1px var(--border); overflow-x: auto; max-width: 100%; scrollbar-width: none; }
.ac-seg::-webkit-scrollbar { display: none; }
.ac-seg-btn {
  display: inline-flex; align-items: center; gap: 7px; min-height: 40px; padding: 0 12px; border: 0;
  border-radius: 9px; background: transparent; color: var(--muted); font-size: 13px; font-weight: 650;
  cursor: pointer; white-space: nowrap; transition: background .15s, color .15s;
}
.ac-seg-btn:hover { color: var(--text); }
.ac-seg-btn.is-active { background: var(--surface-2); color: var(--text); box-shadow: 0 1px 3px rgba(0,0,0,.25); }
.ac-seg-btn .ac-count { font-size: 11.5px; color: var(--muted); font-variant-numeric: tabular-nums; font-weight: 600; }
.ac-dot { width: 8px; height: 8px; border-radius: 3px; flex: 0 0 auto; }
.ac-select {
  height: 44px; padding: 0 30px 0 12px; border-radius: 11px; border: 1px solid var(--border);
  background: var(--surface) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M3 4.5 6 7.5 9 4.5' fill='none' stroke='%23a8a8a8' stroke-width='1.5' stroke-linecap='round'/%3E%3C/svg%3E") no-repeat right 11px center;
  color: var(--text); font-size: 13px; font-weight: 600; appearance: none; cursor: pointer;
}

/* Body and grid */
.ac-body { flex: 1; min-height: 0; display: flex; }
.ac-scroll { flex: 1; min-width: 0; overflow-y: auto; padding: 14px 16px 28px; }
.ac-summary { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 12px;
  margin: 0 2px 12px; color: var(--muted); font-size: 13px; }
.ac-summary-controls { display: flex; gap: 8px; flex-wrap: wrap; }
.ac-select.is-compact { height: 36px; border-radius: 9px; font-size: 12.5px; }
.ac-summary strong { color: var(--text); font-variant-numeric: tabular-nums; }
.ac-understood { margin: -4px 2px 12px; font-size: 12.5px; color: var(--text); }
.ac-understood span { color: var(--muted); margin-right: 4px; }
.ac-notice { display: flex; gap: 8px; align-items: flex-start; margin: 0 0 12px; padding: 10px 12px;
  border-radius: 10px; background: color-mix(in srgb, var(--accent) 9%, var(--surface));
  border: 1px solid color-mix(in srgb, var(--accent) 25%, var(--border)); color: var(--text); font-size: 13px; line-height: 1.45; }
.ac-notice svg { width: 16px; height: 16px; flex: 0 0 auto; margin-top: 1px; color: var(--accent); }
.ac-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(164px, 1fr)); gap: 12px; }
.ac-tile {
  position: relative; display: flex; flex-direction: column; min-width: 0;
  border-radius: 14px; border: 1px solid var(--border); background: var(--surface); color: inherit;
  overflow: hidden; transition: transform .16s ease, border-color .16s, box-shadow .16s;
}
.ac-tile-main { display: flex; flex-direction: column; width: 100%; min-width: 0; padding: 0; border: 0;
  background: transparent; color: inherit; text-align: left; cursor: pointer; font: inherit; }
.ac-tile-main:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; border-radius: 14px; }
.ac-tile.is-sound .ac-thumb { background: radial-gradient(circle at 50% 120%, color-mix(in srgb, var(--ac-sound) 22%, var(--surface-2)), var(--surface-2) 70%); }
.ac-tile.is-sound .ac-thumb img { object-fit: contain; padding: 22% 6%; }
.ac-play {
  position: absolute; top: 8px; right: 8px; z-index: 2; width: 40px; height: 40px; display: grid; place-items: center;
  border-radius: 50%; border: 0; cursor: pointer; color: #0b1716; background: var(--ac-sound);
  box-shadow: 0 4px 14px rgba(0,0,0,.4); transition: transform .15s, filter .15s;
}
.ac-play:hover { filter: brightness(1.08); }
.ac-play svg { width: 18px; height: 18px; }
.ac-play.is-loading { opacity: .75; }
.ac-play.is-playing { background: var(--text); color: var(--bg); }
.ac-tile:hover { border-color: color-mix(in srgb, var(--accent) 50%, var(--border)); box-shadow: 0 10px 28px rgba(0,0,0,.35); }
.ac-tile.is-selected { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent), 0 10px 28px rgba(0,0,0,.35); }
.ac-thumb { position: relative; display: block; aspect-ratio: 1; background: var(--surface-2); overflow: hidden; }
.ac-thumb img { display: block; width: 100%; height: 100%; object-fit: cover; opacity: 0; transition: opacity .25s; }
.ac-thumb img.is-ready { opacity: 1; }
.ac-thumb-fallback { position: absolute; inset: 0; display: grid; place-items: center; color: var(--muted); }
.ac-thumb-fallback svg { width: 34px; height: 34px; opacity: .55; }
.ac-type-badge {
  position: absolute; top: 8px; left: 8px; display: inline-flex; align-items: center; gap: 5px;
  padding: 3px 8px 3px 6px; border-radius: 999px; font-size: 11px; font-weight: 700;
  background: rgba(10,10,10,.62); color: #f1f1f1; backdrop-filter: blur(6px); -webkit-backdrop-filter: blur(6px);
}
.ac-tile-body { display: block; padding: 9px 10px 10px; min-width: 0; }
.ac-tile-title { display: block; font-size: 13px; font-weight: 650; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ac-tile-meta { display: flex; align-items: center; gap: 6px; margin-top: 5px; min-width: 0;
  color: var(--muted); font-size: 11.5px; }
.ac-tile-meta span:last-child { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ac-lic {
  display: inline-flex; align-items: center; height: 19px; padding: 0 7px; border-radius: 6px; flex: 0 0 auto;
  font-size: 10.5px; font-weight: 800; letter-spacing: .02em;
  color: var(--ac-lic); background: color-mix(in srgb, var(--ac-lic) 15%, transparent);
  border: 1px solid color-mix(in srgb, var(--ac-lic) 35%, transparent);
}
.ac-lic.tier-public-domain { --ac-lic: var(--ac-pd); }
.ac-lic.tier-attribution { --ac-lic: var(--ac-by); }
.ac-lic.tier-share-alike { --ac-lic: var(--ac-sa); }
.ac-lic.tier-copyleft { --ac-lic: var(--ac-copyleft); }
.ac-skeleton { aspect-ratio: 1 / 1.24; border-radius: 14px; background: var(--surface); border: 1px solid var(--border); }
@media (prefers-reduced-motion: no-preference) {
  .ac-tile:hover { transform: translateY(-2px); }
  .ac-skeleton { background: linear-gradient(100deg, var(--surface) 30%, var(--surface-2) 50%, var(--surface) 70%);
    background-size: 300% 100%; animation: ac-shimmer 1.4s ease infinite; }
  @keyframes ac-shimmer { from { background-position: 100% 0; } to { background-position: 0 0; } }
  .ac-detail { animation: ac-slide .22s ease; }
  @keyframes ac-slide { from { transform: translateX(16px); opacity: 0; } to { transform: none; opacity: 1; } }
}
.ac-more { display: flex; justify-content: center; margin-top: 18px; }

/* Empty */
.ac-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center;
  gap: 8px; min-height: 46vh; max-width: 460px; margin: 0 auto; padding: 40px 24px; color: var(--muted); }
.ac-empty-mark { width: 60px; height: 60px; margin-bottom: 8px; border-radius: 18px; display: grid; place-items: center;
  background: color-mix(in srgb, var(--accent) 14%, transparent); color: var(--accent);
  border: 1px solid color-mix(in srgb, var(--accent) 30%, var(--border)); }
.ac-empty-mark svg { width: 28px; height: 28px; }
.ac-empty-title { font-size: 17px; font-weight: 700; color: var(--text); }
.ac-empty p { margin: 0; line-height: 1.6; font-size: 14px; }

/* Detail panel */
.ac-detail {
  flex: 0 0 440px; width: 440px; min-width: 0; overflow-y: auto; overflow-x: hidden; border-left: 1px solid var(--border);
  background: var(--surface);
}
.ac-detail-top { position: sticky; top: 0; z-index: 2; display: flex; justify-content: space-between; align-items: center;
  gap: 8px; padding: 10px 12px; background: color-mix(in srgb, var(--surface) 92%, transparent);
  backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px); border-bottom: 1px solid var(--border); }
.ac-detail-top .ac-crumb { font-size: 12px; color: var(--muted); font-weight: 650; display: flex; gap: 6px; align-items: center; }
.ac-hero { position: relative; aspect-ratio: 1.25; background: var(--surface-2); overflow: hidden; }
.ac-hero img { width: 100%; height: 100%; object-fit: cover; display: block; }
.ac-hero.is-hdri { aspect-ratio: 2; }
.ac-hero.is-sound { aspect-ratio: 2.6; background: radial-gradient(circle at 50% 130%, color-mix(in srgb, var(--ac-sound) 25%, var(--surface-2)), var(--surface-2) 70%); }
.ac-hero.is-sound img { object-fit: contain; padding: 18px 16px; }
.ac-detail-main { padding: 16px 18px 28px; display: flex; flex-direction: column; gap: 18px; overflow-wrap: anywhere; }
.ac-detail h2 { margin: 0; font-size: 21px; line-height: 1.2; letter-spacing: -0.02em; }
.ac-byline { margin: 6px 0 0; color: var(--muted); font-size: 13px; line-height: 1.5; }
.ac-byline a { color: var(--text); text-decoration: none; border-bottom: 1px solid var(--border); }
.ac-byline a:hover { border-color: var(--accent); }
.ac-desc { margin: 0; color: var(--muted); line-height: 1.55; font-size: 13.5px; }
.ac-section-label { margin: 0 0 8px; font-size: 11.5px; font-weight: 750; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); }
.ac-license-card { padding: 12px 14px; border-radius: 12px; border: 1px solid color-mix(in srgb, var(--ac-lic) 35%, var(--border));
  background: color-mix(in srgb, var(--ac-lic) 8%, var(--surface)); }
.ac-license-card.tier-public-domain { --ac-lic: var(--ac-pd); }
.ac-license-card.tier-attribution { --ac-lic: var(--ac-by); }
.ac-license-card.tier-share-alike { --ac-lic: var(--ac-sa); }
.ac-license-card.tier-copyleft { --ac-lic: var(--ac-copyleft); }
.ac-license-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.ac-license-head strong { font-size: 14px; }
.ac-license-card p { margin: 6px 0 0; font-size: 13px; line-height: 1.5; color: var(--muted); }
.ac-credit { margin-top: 10px; display: flex; gap: 8px; align-items: flex-start; }
.ac-credit code { flex: 1; display: block; padding: 8px 10px; border-radius: 8px; background: var(--bg);
  border: 1px solid var(--border); font-family: var(--mono); font-size: 11.5px; line-height: 1.5; color: var(--text);
  user-select: all; word-break: break-word; }
.ac-specs { display: flex; flex-wrap: wrap; gap: 6px; }
.ac-spec { padding: 5px 9px; border-radius: 8px; background: var(--surface-2); border: 1px solid var(--border);
  font-size: 12px; font-weight: 600; font-variant-numeric: tabular-nums; }
.ac-spec em { font-style: normal; color: var(--muted); font-weight: 500; margin-right: 4px; }
.ac-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.ac-chip { display: inline-flex; align-items: center; gap: 5px; min-height: 30px; padding: 0 10px; border-radius: 999px;
  border: 1px solid var(--border); background: transparent; color: var(--muted); font-size: 12px; font-weight: 600; cursor: pointer; }
.ac-chip:hover { color: var(--text); border-color: color-mix(in srgb, var(--accent) 50%, var(--border)); }
.ac-variants { display: flex; flex-direction: column; border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
.ac-variant { display: flex; align-items: center; gap: 10px; min-height: 46px; padding: 6px 8px 6px 12px; border-top: 1px solid var(--border); }
.ac-variant:first-child { border-top: 0; }
.ac-variant.is-default { background: color-mix(in srgb, var(--accent) 7%, transparent); }
.ac-variant-label { flex: 1; min-width: 0; font-size: 13px; font-weight: 600; }
.ac-variant-label small { display: block; margin-top: 1px; font-size: 11.5px; color: var(--muted); font-weight: 500; }
.ac-variant-size { font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums; }
.ac-variants-more { padding: 8px 12px; border-top: 1px solid var(--border); }
.ac-agent-box { padding: 12px 14px; border-radius: 12px; background: var(--bg); border: 1px dashed color-mix(in srgb, var(--accent) 45%, var(--border)); }
.ac-agent-box p { margin: 0 0 8px; font-size: 13px; line-height: 1.5; color: var(--muted); }
.ac-agent-box code { display: block; padding: 8px 10px; border-radius: 8px; background: var(--surface); font-family: var(--mono);
  font-size: 11.5px; line-height: 1.5; user-select: all; word-break: break-word; }
.ac-agent-actions { display: flex; gap: 8px; margin-top: 10px; }
.ac-notes ol { margin: 10px 0 0; padding-left: 18px; display: flex; flex-direction: column; gap: 7px; }
.ac-notes li { font-size: 13px; line-height: 1.5; color: var(--text); }
.ac-notes code { font-family: var(--mono); font-size: 12px; }
.ac-related { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.ac-related button { padding: 0; border: 1px solid var(--border); border-radius: 10px; overflow: hidden; background: var(--surface-2);
  cursor: pointer; aspect-ratio: 1; position: relative; }
.ac-related button:hover { border-color: var(--accent); }
.ac-related img { width: 100%; height: 100%; object-fit: cover; display: block; }
.ac-error-text { color: var(--danger); font-size: 13px; }

/* Sheet (agents / sources info) */
.ac-scrim { position: absolute; inset: 0; z-index: 50; display: flex; align-items: center; justify-content: center;
  padding: 16px; background: rgba(0,0,0,.55); }
.ac-sheet { width: 100%; max-width: 620px; max-height: 88%; overflow-y: auto; padding: 22px 22px 24px;
  background: var(--surface); border: 1px solid var(--border); border-radius: 18px; box-shadow: 0 24px 60px rgba(0,0,0,.5); }
.ac-sheet h3 { margin: 0 0 6px; font-size: 18px; letter-spacing: -0.01em; }
.ac-sheet .ac-section-label { margin: 0 0 8px; font-size: 11.5px; letter-spacing: .06em; }
.ac-sheet > p { margin: 0 0 14px; color: var(--muted); line-height: 1.55; }
.ac-tool-list { display: flex; flex-direction: column; gap: 8px; margin: 12px 0 18px; }
.ac-tool { padding: 10px 12px; border-radius: 10px; background: var(--bg); border: 1px solid var(--border); }
.ac-tool code { font-family: var(--mono); font-size: 12.5px; color: var(--accent); }
.ac-tool p { margin: 4px 0 0; font-size: 13px; color: var(--muted); line-height: 1.45; }
.ac-source-row { display: flex; align-items: center; gap: 10px; padding: 9px 0; border-top: 1px solid var(--border); font-size: 13px; }
.ac-source-row:first-child { border-top: 0; }
.ac-source-row strong { min-width: 110px; }
.ac-source-row > span:not(.ac-pill) { flex: 1; color: var(--muted); }
.ac-source-row .ac-pill { flex: 0 0 auto; }
.ac-pill { padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; background: var(--surface-2); color: var(--muted); }
.ac-pill.is-live { color: var(--ac-pd); background: color-mix(in srgb, var(--ac-pd) 14%, transparent); }
.ac-source-progress { display: block; margin-top: 4px; font-style: normal; color: var(--text); opacity: .85; }
.ac-license-card .ac-source-note { font-size: 12.5px; }
.ac-toast { position: absolute; left: 50%; bottom: 18px; transform: translateX(-50%); z-index: 60; padding: 9px 14px;
  border-radius: 10px; background: var(--text); color: var(--bg); font-size: 13px; font-weight: 650; box-shadow: 0 8px 24px rgba(0,0,0,.4); }

/* Tools directory */
.ac-tool-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }
.ac-tool-card { display: flex; flex-direction: column; gap: 7px; min-width: 0; padding: 14px; text-align: left;
  border-radius: 14px; border: 1px solid var(--border); background: var(--surface); color: inherit; font: inherit; cursor: pointer;
  transition: border-color .15s, box-shadow .15s; }
.ac-tool-card:hover { border-color: color-mix(in srgb, var(--accent) 50%, var(--border)); box-shadow: 0 8px 22px rgba(0,0,0,.3); }
.ac-tool-card:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.ac-tool-card.is-compact { padding: 11px 12px; gap: 5px; }
.ac-tool-card-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.ac-kind { font-size: 10.5px; font-weight: 800; letter-spacing: .05em; text-transform: uppercase; padding: 3px 7px; border-radius: 6px;
  background: color-mix(in srgb, var(--accent) 14%, transparent); color: color-mix(in srgb, var(--accent) 70%, var(--text)); }
.ac-kind.kind-library { background: color-mix(in srgb, var(--ac-pd) 14%, transparent); color: var(--ac-pd); }
.ac-kind.kind-tool { background: color-mix(in srgb, var(--ac-hdri) 14%, transparent); color: var(--ac-hdri); }
.ac-price { font-size: 11.5px; color: var(--muted); font-weight: 600; }
.ac-tool-name { font-size: 15px; font-weight: 700; letter-spacing: -0.01em; }
.ac-unreviewed { font-size: 11.5px; font-weight: 600; color: var(--muted); }
.ac-tool-summary { font-size: 13px; line-height: 1.45; color: var(--muted); display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.ac-tool-meta { font-size: 11.5px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ac-tool-strip { margin: 0 0 16px; padding: 12px; border-radius: 14px; border: 1px dashed color-mix(in srgb, var(--accent) 35%, var(--border)); }
.ac-tool-strip.is-prominent { background: color-mix(in srgb, var(--accent) 7%, var(--surface)); border-style: solid; }
.ac-tool-row { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 8px; }
.ac-form label { display: flex; flex-direction: column; gap: 5px; margin-bottom: 10px; font-size: 12.5px; font-weight: 650; color: var(--muted); }
.ac-form input, .ac-form textarea { padding: 9px 11px; border-radius: 9px; border: 1px solid var(--border); background: var(--bg); color: var(--text);
  font: inherit; font-size: 14px; font-weight: 500; }
.ac-form input:focus, .ac-form textarea:focus { outline: 2px solid var(--accent); outline-offset: 1px; }
.ac-form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.ac-notes-list { display: flex; flex-direction: column; gap: 8px; }
.ac-note { display: grid; grid-template-columns: auto 1fr; gap: 4px 10px; padding: 9px 11px; border-radius: 10px; background: var(--bg); border: 1px solid var(--border); }
.ac-note-tag { grid-row: span 2; align-self: start; font-size: 10.5px; font-weight: 800; text-transform: uppercase; letter-spacing: .04em;
  padding: 3px 6px; border-radius: 6px; background: var(--surface-2); color: var(--muted); }
.ac-note.outcome-worked .ac-note-tag { color: var(--ac-pd); background: color-mix(in srgb, var(--ac-pd) 14%, transparent); }
.ac-note.outcome-problem .ac-note-tag { color: var(--ac-copyleft); background: color-mix(in srgb, var(--ac-copyleft) 14%, transparent); }
.ac-note-text { font-size: 13px; line-height: 1.45; }
.ac-note-meta { font-size: 11.5px; color: var(--muted); display: flex; gap: 8px; align-items: center; }
.ac-link-btn { border: 0; background: none; padding: 0; color: var(--muted); font: inherit; font-size: 11.5px; cursor: pointer; text-decoration: underline; }
.ac-note-form { display: flex; gap: 8px; align-items: center; }
.ac-note-form input { flex: 1; min-width: 0; height: 36px; padding: 0 10px; border-radius: 9px; border: 1px solid var(--border); background: var(--bg); color: var(--text); font: inherit; font-size: 13px; }
.ac-contents { display: flex; flex-wrap: wrap; gap: 5px; }
.ac-contents span { padding: 3px 8px; border-radius: 7px; background: var(--surface-2); font-size: 12px; color: var(--muted); }
.ac-contents span.is-hit { color: var(--text); background: color-mix(in srgb, var(--accent) 16%, transparent); }
.ac-seg-btn.is-tools { color: var(--text); }

/* Sources sheet */
.ac-source-card { padding: 14px 16px; border-radius: 14px; border: 1px solid var(--border); background: var(--bg); }
.ac-source-card-head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.ac-source-card h4 { margin: 0; font-size: 15px; }
.ac-source-card-head p { margin: 3px 0 0; color: var(--muted); font-size: 13px; }
.ac-source-status { display: flex; gap: 7px; align-items: center; margin: 12px 0 6px; font-size: 13.5px; font-weight: 650; }
.ac-source-status svg { width: 17px; height: 17px; color: var(--ac-pd); }
.ac-steps { margin: 12px 0; padding-left: 20px; display: flex; flex-direction: column; gap: 6px; font-size: 13.5px; line-height: 1.5; }
.ac-steps a { color: var(--accent); text-decoration: none; display: inline-flex; align-items: center; gap: 3px; font-weight: 650; }
.ac-steps a svg { width: 13px; height: 13px; }
.ac-key-form { display: flex; gap: 8px; flex-wrap: wrap; }
.ac-key-form .ac-search { flex: 1 1 240px; }
.ac-fine { margin: 10px 0 0; font-size: 12.5px; line-height: 1.5; color: var(--muted); }
.ac-cta-row { display: flex; justify-content: center; margin-top: 6px; }

/* Narrow screens: the detail becomes a full-height sheet over the grid */
@media (max-width: 900px) {
  .ac-detail { position: absolute; inset: 0; z-index: 40; width: auto; flex: none; border-left: 0; }
  .ac-header-right .ac-btn-label { display: none; }
  .ac-toolbar { padding: 10px 12px; }
  .ac-scroll { padding: 12px 12px 24px; }
  .ac-grid { grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px; }
}
`
