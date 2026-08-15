// Extracted from App.tsx (pure move, no behaviour change).
import type { Insights } from '@/lib/api'

// ---- readout rail ----------------------------------------------------------

export const TOP_SKILLS = 10

/** Bar fill for a demanded skill.
 *
 * Deliberately redundant: the two states differ by COLOUR (blue vs amber, chosen
 * in index.css to sit on the blue-yellow axis rather than the red-green one),
 * by LIGHTNESS, and by TEXTURE. A gap bar is striped, so the distinction survives
 * greyscale printing and any form of colour blindness — colour alone is never
 * the only cue. `title` gives the same information to a screen reader.
 */
export function barFill(candidateHas: boolean): { background: string } {
  if (candidateHas) return { background: 'var(--have)' }
  return {
    background:
      'repeating-linear-gradient(135deg, var(--gap) 0 3px, color-mix(in oklab, var(--gap) 45%, var(--paper)) 3px 6px)',
  }
}

export function ReadoutRail({ insights, analyzing, scoreColor, className }: { insights: Insights | null; analyzing: boolean; scoreColor: (n: number) => string; className?: string }) {
  return (
    <aside className={className} style={{ borderLeft: '2px solid var(--ink)', minWidth: 0 }}>
      <div className="ov-micro" style={{ padding: '11px 16px', borderBottom: '1px solid var(--rule)', fontSize: 9 }}>
        readout{insights ? ` · ${insights.job_count} jobs` : ''}
      </div>
      {insights ? (
        <div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', borderBottom: '1px solid var(--rule)' }}>
            {[
              ['avg match', insights.coverage ? `${insights.coverage.avg_relevance}%` : '—', insights.coverage ? scoreColor(insights.coverage.avg_relevance) : 'var(--ink)'],
              ['strong ≥60', insights.coverage ? String(insights.coverage.strong_matches) : '—', 'var(--ink)'],
              ['salary to', insights.salary?.max ? insights.salary.max.toLocaleString() : '—', 'var(--ink)'],
              ['jobs', String(insights.job_count), 'var(--ink)'],
            ].map(([cap, val, col], i) => (
              <div key={cap} style={{ padding: '12px 16px', borderRight: i % 2 === 0 ? '1px solid var(--rule)' : undefined, borderTop: i >= 2 ? '1px solid var(--rule)' : undefined }}>
                <div className="ov-micro" style={{ fontSize: 9 }}>{cap}</div>
                <div className="ov-num" style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 22, color: col as string, marginTop: 4 }}>{val}</div>
              </div>
            ))}
          </div>
          <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--rule)' }}>
            <div className="ov-micro" style={{ fontSize: 9, marginBottom: 10 }}>demand vs you</div>
            {insights.demanded_skills.slice(0, TOP_SKILLS).map((d) => (
              <div key={d.skill} style={{ display: 'grid', gridTemplateColumns: '1fr 34px', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <div>
                  <div className="ov-mono" style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--dim)', marginBottom: 3 }}>{d.skill}</div>
                  <div style={{ display: 'flex', height: 7, background: 'var(--hair)' }}>
                    <div
                      data-state={d.candidate_has ? 'have' : 'gap'}
                      title={d.candidate_has ? 'in your cv' : 'gap to close'}
                      style={{ width: `${d.pct}%`, ...barFill(d.candidate_has) }}
                    />
                  </div>
                </div>
                <span className="ov-mono ov-num" style={{ fontFamily: 'var(--font-mono)', fontSize: 11, textAlign: 'right', color: 'var(--dim)' }}>{d.pct}%</span>
              </div>
            ))}
            <div className="ov-micro" style={{ fontSize: 8, marginTop: 8, lineHeight: 1.6 }}>
              solid bar = in your cv / striped bar = gap to close
            </div>
          </div>
        </div>
      ) : analyzing ? (
        <div className="ov-micro" style={{ padding: '16px', fontSize: 9 }}>▸ analyzing insights…</div>
      ) : (
        <div className="ov-micro" style={{ padding: '16px', fontSize: 9, lineHeight: 1.7 }}>cv + results live in your browser (localstorage). name, email + phone are stripped before the ai tailors it, then restored locally. never stored.</div>
      )}
    </aside>
  )
}
