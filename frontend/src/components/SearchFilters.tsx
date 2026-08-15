// Extracted from App.tsx (pure move, no behaviour change).
import { type ReactNode } from 'react'
import {
  DATE_OPTIONS, EXPERIENCE_OPTIONS, PLATFORM_OPTIONS, REMOTE_OPTIONS, MAX_JOBS_OPTIONS,
  SALARY_OPTIONS, type FilterState,
} from '@/lib/search-filters'
import { filterSupport, type Capabilities } from '@/lib/capabilities'
import { BoardFilters } from '@/components/BoardFilters'

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

export function FilterBtn({ active, onClick, children, disabled, title }: {
  active: boolean; onClick: () => void; children: ReactNode; disabled?: boolean; title?: string
}) {
  return (
    <button onClick={onClick} disabled={disabled} title={title} className="ov-mono"
      style={{ fontFamily: 'var(--font-mono)', fontSize: 11, padding: '8px 12px', borderRight: '1px solid var(--rule)', cursor: disabled ? 'not-allowed' : 'pointer', whiteSpace: 'nowrap', background: active && !disabled ? 'var(--ink)' : 'transparent', color: disabled ? 'var(--rule)' : active ? 'var(--paper)' : 'var(--dim)', fontWeight: active && !disabled ? 700 : 400, opacity: disabled ? 0.45 : 1 }}>
      {children}
    </button>
  )
}

export function FilterRows({ filters, setDate, setMax, toggleFilter, selectBoard, caps, setMinSalary, setPlatformFilters }: {
  filters: FilterState; setDate: (v: string) => void; setMax: (n: number) => void
  toggleFilter: (k: 'experienceLevels' | 'remoteOptions', v: string) => void
  selectBoard: (platform: string | null) => void
  caps: Capabilities | null
  setMinSalary: (n: number | null) => void
  setPlatformFilters: (platform: string, next: Record<string, unknown>) => void
}) {
  // Which of the shared filters the CURRENT board selection can actually honour.
  // Replaces the old hardcoded "li only" / "li + mcf only" captions, both of which
  // were measured wrong: LinkedIn honours neither, JobStreet honours remote.
  const exp = filterSupport(caps, filters.platforms, 'experience_levels')
  const remote = filterSupport(caps, filters.platforms, 'remote_options')
  const salary = filterSupport(caps, filters.platforms, 'min_salary')
  const unavailable = 'not available for the selected boards'
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
      <FilterRow label="board" note={filters.platforms.length === 1 ? 'gets the whole budget' : 'budget splits across all four'}>
        {/* Single choice, not a multi-select. Board-native filters below only exist
            for one board at a time, so an arbitrary subset has no coherent panel to
            show and used to leave a hidden filter applied. */}
        <FilterBtn active={filters.platforms.length === 0} onClick={() => selectBoard(null)}>
          All boards
        </FilterBtn>
        {PLATFORM_OPTIONS.map((o) => (
          <FilterBtn key={o.value} active={filters.platforms[0] === o.value}
            onClick={() => selectBoard(o.value)}>{o.label}</FilterBtn>
        ))}
      </FilterRow>
      <FilterRow label="experience" note={exp.usable ? undefined : unavailable}>
        {EXPERIENCE_OPTIONS.map((o) => (
          <FilterBtn key={o.value} active={filters.experienceLevels.includes(o.value)}
            disabled={!exp.usable} title={exp.reason}
            onClick={() => toggleFilter('experienceLevels', o.value)}>{o.label}</FilterBtn>
        ))}
      </FilterRow>
      <FilterRow label="remote" note={remote.usable ? undefined : unavailable}>
        {REMOTE_OPTIONS.map((o) => (
          <FilterBtn key={o.value} active={filters.remoteOptions.includes(o.value)}
            disabled={!remote.usable} title={remote.reason}
            onClick={() => toggleFilter('remoteOptions', o.value)}>{o.label}</FilterBtn>
        ))}
      </FilterRow>
      <FilterRow label="min salary" note={salary.usable ? 'monthly, can pay at least' : unavailable}>
        {SALARY_OPTIONS.map((n) => (
          <FilterBtn key={n} active={(filters.minSalary ?? 0) === n}
            disabled={!salary.usable} title={salary.reason}
            onClick={() => setMinSalary(n === 0 ? null : n)}>
            {n === 0 ? 'any' : `${n / 1000}k+`}
          </FilterBtn>
        ))}
      </FilterRow>
      {filters.platforms.length === 1 && (
        <BoardFilters
          caps={caps}
          platform={filters.platforms[0]}
          value={filters.platformFilters[filters.platforms[0]] ?? {}}
          onChange={(next) => setPlatformFilters(filters.platforms[0], next)}
        />
      )}
    </div>
  )
}
