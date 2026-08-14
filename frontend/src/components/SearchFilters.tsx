// Extracted from App.tsx (pure move, no behaviour change).
import { type ReactNode } from 'react'
import {
  DATE_OPTIONS, EXPERIENCE_OPTIONS, PLATFORM_OPTIONS, REMOTE_OPTIONS, MAX_JOBS_OPTIONS,
  type FilterState,
} from '@/lib/search-filters'

// ---- filter rows -----------------------------------------------------------

export function FilterRow({ label, note, children }: { label: string; note?: string; children: ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'stretch', borderBottom: '1px solid var(--rule)', flexWrap: 'wrap' }}>
      <span className="ov-micro" style={{ width: 110, flexShrink: 0, padding: '8px 12px', borderRight: '1px solid var(--rule)', fontSize: 9, alignSelf: 'center' }}>{label}</span>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', flex: 1 }}>{children}</div>
      {note && <span className="ov-micro" style={{ marginLeft: 'auto', alignSelf: 'center', padding: '0 12px', fontSize: 9, color: 'var(--dim)' }}>{note}</span>}
    </div>
  )
}

export function FilterBtn({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button onClick={onClick} className="ov-mono"
      style={{ fontFamily: 'var(--font-mono)', fontSize: 11, padding: '8px 12px', borderRight: '1px solid var(--rule)', cursor: 'pointer', whiteSpace: 'nowrap', background: active ? 'var(--ink)' : 'transparent', color: active ? 'var(--paper)' : 'var(--dim)', fontWeight: active ? 700 : 400 }}>
      {children}
    </button>
  )
}

export function FilterRows({ filters, setDate, setMax, toggleFilter }: {
  filters: FilterState; setDate: (v: string) => void; setMax: (n: number) => void
  toggleFilter: (k: 'experienceLevels' | 'remoteOptions' | 'platforms', v: string) => void
}) {
  return (
    <div style={{ borderBottom: '2px solid var(--ink)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', background: 'var(--panel)', borderBottom: '1px solid var(--rule)', flexWrap: 'wrap' }}>
        <span className="ov-micro" style={{ fontSize: 9, color: 'var(--ink)' }}>▸ search filters</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--dim)' }}>what gets scraped — apply on execute</span>
      </div>
      <FilterRow label="date">
        {DATE_OPTIONS.map((o) => <FilterBtn key={o.value} active={filters.datePosted === o.value} onClick={() => setDate(o.value)}>{o.label}</FilterBtn>)}
      </FilterRow>
      <FilterRow label="max jobs">
        {MAX_JOBS_OPTIONS.map((n) => <FilterBtn key={n} active={filters.maxJobs === n} onClick={() => setMax(n)}>{n}</FilterBtn>)}
      </FilterRow>
      <FilterRow label="boards" note="none = every board">
        {PLATFORM_OPTIONS.map((o) => <FilterBtn key={o.value} active={filters.platforms.includes(o.value)} onClick={() => toggleFilter('platforms', o.value)}>{o.label}</FilterBtn>)}
      </FilterRow>
      <FilterRow label="experience" note="li + mcf only">
        {EXPERIENCE_OPTIONS.map((o) => <FilterBtn key={o.value} active={filters.experienceLevels.includes(o.value)} onClick={() => toggleFilter('experienceLevels', o.value)}>{o.label}</FilterBtn>)}
      </FilterRow>
      <FilterRow label="remote" note="li only">
        {REMOTE_OPTIONS.map((o) => <FilterBtn key={o.value} active={filters.remoteOptions.includes(o.value)} onClick={() => toggleFilter('remoteOptions', o.value)}>{o.label}</FilterBtn>)}
      </FilterRow>
    </div>
  )
}
