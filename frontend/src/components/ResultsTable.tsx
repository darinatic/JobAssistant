// Extracted from App.tsx (pure move, no behaviour change).
import type { Job } from '@/lib/api'
import { applyRefine, type RefineState } from '@/lib/jobfmt'
import { jobKey } from '@/lib/app-utils'
import { FitBadge, JobMeta, SalaryLevel, Tokens } from '@/components/shared/primitives'
import { RefineBar } from '@/components/RefineBar'

// ---- results table ---------------------------------------------------------

export function ResultsTable({ jobs, pending, allFits, onOpen, refine, setRefine }: {
  jobs: Job[]; pending: Set<string>; allFits: number[]; onOpen: (j: Job) => void
  refine: RefineState; setRefine: (u: RefineState) => void
}) {
  const scored = jobs.filter((job) => !pending.has(jobKey(job)))
  if (!scored.length) return null
  const visible = applyRefine(scored, refine, allFits)
  return (
    <div>
      <RefineBar jobs={scored} allFits={allFits} refine={refine} setRefine={setRefine} visibleCount={visible.length} />
      <div className="ov-jobrow" style={{ background: 'var(--panel)', borderBottom: '1px solid var(--rule)' }}>
        <span className="ov-micro ov-jobrow-idx" style={{ fontSize: 9, padding: '8px 12px' }}>#</span>
        <span className="ov-micro ov-jobrow-role" style={{ fontSize: 9, padding: '8px 12px' }}>role</span>
        <span className="ov-micro ov-jobrow-salary" style={{ fontSize: 9, padding: '8px 12px', textAlign: 'right' }}>salary</span>
        <span className="ov-micro ov-jobrow-verdict" style={{ fontSize: 9, padding: '8px 12px' }}>verdict</span>
      </div>
      {visible.length === 0 ? (
        <div className="ov-micro" style={{ fontSize: 9, padding: '16px 20px', color: 'var(--dim)' }}>no jobs match these refine filters.</div>
      ) : visible.map((job, idx) => {
        const have = job.matched_skills ?? []
        const missing = job.missing_skills ?? []
        const total = have.length + missing.length
        return (
          <button key={jobKey(job)} onClick={() => onOpen(job)}
            className="ov-jobrow"
            style={{ width: '100%', textAlign: 'left', borderBottom: '1px solid var(--rule)', borderLeft: '3px solid transparent', background: 'transparent', cursor: 'pointer', padding: 0 }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--hair)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}>
            <span className="ov-num ov-jobrow-idx" style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--dim)', padding: '12px' }}>{String(idx + 1).padStart(2, '0')}</span>
            <div className="ov-jobrow-role" style={{ padding: '12px', minWidth: 0 }}>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 16, letterSpacing: '-0.015em', color: 'var(--ink)', lineHeight: 1.2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{job.title}</div>
              <div style={{ marginTop: 4 }}><JobMeta job={job} /></div>
              {total > 0 ? (
                <div style={{ marginTop: 6, display: 'flex', flexWrap: 'wrap' }}><Tokens have={have} missing={missing} /></div>
              ) : (
                <div className="ov-micro" style={{ fontSize: 9, color: 'var(--gap)', marginTop: 6 }}>no description returned · open to fetch</div>
              )}
            </div>
            <div className="ov-jobrow-salary" style={{ padding: '12px', textAlign: 'right' }}><SalaryLevel job={job} /></div>
            <div className="ov-jobrow-verdict" style={{ padding: '12px' }}>
              {job.below_threshold ? <span className="ov-stamp ov-stamp-moderate">closest</span>
                : job.fit != null ? <FitBadge fit={job.fit} allFits={allFits} />
                : <span className="ov-stamp" style={{ border: '1.5px dashed var(--dim)', color: 'var(--dim)' }}>unrated</span>}
            </div>
          </button>
        )
      })}
    </div>
  )
}
