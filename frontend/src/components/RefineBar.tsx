// Extracted from App.tsx (pure move, no behaviour change).
import type { Job } from '@/lib/api'
import { hasSalary, jobTier, refineActive, levelLabel, EMPTY_REFINE, LEVEL_ORDER,
  type RefineState, type Tier } from '@/lib/jobfmt'
import { FilterRow, FilterBtn } from '@/components/SearchFilters'

// ---- refine bar (client-side, over the already-fetched results) ------------

export const MIN_SALARY_OPTS = [0, 3000, 5000, 8000, 10000]
export const TIER_OPTS: [Tier, string][] = [
  ['top', 'top fit'], ['strong', 'strong'], ['moderate', 'moderate'], ['weak', 'weak'], ['unrated', 'unrated'],
]

export function RefineBar({ jobs, allFits, refine, setRefine, visibleCount }: {
  jobs: Job[]; allFits: number[]; refine: RefineState; setRefine: (u: RefineState) => void; visibleCount: number
}) {
  const levelsPresent = LEVEL_ORDER.filter((l) => jobs.some((j) => j.experience_level === l))
  const platformsPresent = [...new Set(jobs.map((j) => j.platform))]
  const tiersPresent = TIER_OPTS.filter(([t]) => jobs.some((j) => jobTier(j, allFits) === t))
  const anySalary = jobs.some(hasSalary)
  const active = refineActive(refine)

  const toggle = (key: 'levels' | 'platforms', v: string) =>
    setRefine({ ...refine, [key]: refine[key].includes(v) ? refine[key].filter((x) => x !== v) : [...refine[key], v] })
  const toggleTier = (t: Tier) =>
    setRefine({ ...refine, tiers: refine.tiers.includes(t) ? refine.tiers.filter((x) => x !== t) : [...refine.tiers, t] })

  return (
    <div style={{ borderBottom: '2px solid var(--ink)', borderLeft: '3px solid var(--geo)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, padding: '8px 17px', background: 'color-mix(in oklab, var(--geo) 6%, transparent)', borderBottom: '1px solid var(--rule)', flexWrap: 'wrap' }}>
        <span className="ov-micro" style={{ fontSize: 9, color: 'var(--geo)' }}>▾ refine · filters the {jobs.length} results below, no new search · {visibleCount} shown</span>
        {active && <button onClick={() => setRefine(EMPTY_REFINE)} className="ov-micro" style={{ fontSize: 9, background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--dim)' }}>reset ✕</button>}
      </div>
      {levelsPresent.length > 0 && (
        <FilterRow label="experience">
          {levelsPresent.map((l) => <FilterBtn key={l} active={refine.levels.includes(l)} onClick={() => toggle('levels', l)}>{levelLabel(l)}</FilterBtn>)}
        </FilterRow>
      )}
      {platformsPresent.length > 1 && (
        <FilterRow label="board">
          {platformsPresent.map((p) => <FilterBtn key={p} active={refine.platforms.includes(p)} onClick={() => toggle('platforms', p)}>{p}</FilterBtn>)}
        </FilterRow>
      )}
      {tiersPresent.length > 1 && (
        <FilterRow label="fit">
          {tiersPresent.map(([t, label]) => <FilterBtn key={t} active={refine.tiers.includes(t)} onClick={() => toggleTier(t)}>{label}</FilterBtn>)}
        </FilterRow>
      )}
      {anySalary && (
        <FilterRow label="salary">
          <FilterBtn active={refine.hasSalaryOnly} onClick={() => setRefine({ ...refine, hasSalaryOnly: !refine.hasSalaryOnly })}>disclosed</FilterBtn>
          {MIN_SALARY_OPTS.map((n) => (
            <FilterBtn key={n} active={refine.minSalary === n} onClick={() => setRefine({ ...refine, minSalary: n })}>
              {n === 0 ? 'any' : `${n / 1000}k+/mo`}
            </FilterBtn>
          ))}
        </FilterRow>
      )}
    </div>
  )
}
