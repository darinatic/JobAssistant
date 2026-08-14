// Extracted from App.tsx (pure move, no behaviour change).
// ---- paste jd --------------------------------------------------------------

export function PasteJd({ url, setUrl, jd, setJd, fetchingUrl, onFetchUrl, onTailor, tailoring }: {
  url: string; setUrl: (v: string) => void; jd: string; setJd: (v: string) => void
  fetchingUrl: boolean; onFetchUrl: () => void; onTailor: () => void; tailoring: boolean
}) {
  return (
    <div className="ov-pad">
      <div style={{ display: 'flex', border: '2px solid var(--ink)' }}>
        <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="Paste a job posting URL to auto-extract…"
          style={{ flex: 1, minWidth: 0, border: 'none', outline: 'none', background: 'transparent', fontFamily: 'var(--font-mono)', fontSize: 13, padding: '12px 14px', color: 'var(--ink)' }} />
        <button onClick={onFetchUrl} disabled={fetchingUrl} className="ov-btn" style={{ border: 'none', borderLeft: '2px solid var(--ink)' }}>{fetchingUrl ? 'fetching…' : 'fetch jd'}</button>
      </div>
      <div className="ov-micro" style={{ fontSize: 9, margin: '12px 0 8px' }}>…or paste the description</div>
      <textarea value={jd} onChange={(e) => setJd(e.target.value)} placeholder="Paste the full job description here"
        style={{ width: '100%', minHeight: 300, border: '2px solid var(--ink)', outline: 'none', background: 'var(--surface)', fontFamily: 'var(--font-mono)', fontSize: 13, lineHeight: 1.7, padding: 16, color: 'var(--ink)', resize: 'vertical' }} />
      <button className="ov-btn ov-btn-ink" style={{ marginTop: 14 }} onClick={onTailor} disabled={tailoring}>choose style &amp; tailor →</button>
    </div>
  )
}
