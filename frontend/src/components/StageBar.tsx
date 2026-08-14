// Extracted from App.tsx (pure move, no behaviour change).
import type { View } from '@/lib/app-types'

// ---- stage bar -------------------------------------------------------------

export function StageBar({ view, cv, hasJob, onGo }: { view: View; cv: boolean; hasJob: boolean; onGo: (v: View) => void }) {
  const items: [View, string, boolean][] = [
    ['upload', '01 resume', true],
    ['search', '02 search', cv],
    ['job', '03 tailor', hasJob],
  ]
  return (
    <header style={{ position: 'sticky', top: 0, zIndex: 20, display: 'flex', alignItems: 'stretch', background: 'var(--surface)', borderBottom: '2px solid var(--ink)' }}>
      <a href="/" style={{ background: 'var(--ink)', color: 'var(--paper)', fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 14, padding: '0 16px', textDecoration: 'none', display: 'flex', alignItems: 'center' }}>OVERLAP</a>
      <nav role="tablist" style={{ display: 'flex' }}>
        {items.map(([v, label, enabled]) => (
          <button key={v} role="tab" aria-selected={view === v} disabled={!enabled} onClick={() => onGo(v)}
            className="ov-mono"
            style={{
              fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 11, letterSpacing: '0.14em', textTransform: 'uppercase',
              padding: '0 20px', minHeight: 46, borderRight: '1px solid var(--rule)', cursor: enabled ? 'pointer' : 'not-allowed',
              background: view === v ? 'var(--ink)' : 'transparent', color: view === v ? 'var(--paper)' : enabled ? 'var(--dim)' : 'var(--hair)',
            }}>
            {label}
          </button>
        ))}
      </nav>
      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8, padding: '0 16px' }}>
        <span style={{ width: 9, height: 9, background: cv ? 'var(--have)' : 'var(--gap)', display: 'inline-block' }} />
        <span className="ov-micro ov-hide-sm" style={{ fontSize: 9 }}>{cv ? `cv loaded · local` : 'no cv · local'}</span>
      </div>
    </header>
  )
}
