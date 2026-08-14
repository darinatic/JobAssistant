// Extracted from App.tsx (pure move, no behaviour change).
import { toast } from 'sonner'
import type { Job, RedFlag, TailorResult } from '@/lib/api'
import { api } from '@/lib/api'
import { ResumeWorkspace } from '@/components/ResumeWorkspace'
import { estimatePageTarget } from '@/lib/page-fit'
import { formatSalary, experienceLabel } from '@/lib/jobfmt'
import { patchSkillsLine, skillInResume } from '@/lib/skills'
import { download, err } from '@/lib/app-utils'
import { SegmentedBar } from '@/overlap/SegmentedBar'
import { STYLES, type ActiveJob } from '@/lib/app-types'
import {
  Coverage, FitBadge, GuardrailPanel, JobMeta, SalaryLevel, SkillChip, Tokens,
} from '@/components/shared/primitives'

// ---- stage 03 tailor -------------------------------------------------------

export function Pipeline({ tailoring, result, downloading }: { tailoring: boolean; result: TailorResult | null; downloading: string | null }) {
  // Real stream stages, not a guess: `result` appears when the match event lands,
  // and only flips to 'completed' on `done`. Lighting the tailor/lint dots off
  // `!!result` would have claimed both were finished the moment matching ended.
  const matched = !!result
  const done = result?.status === 'completed'
  const rows: [string, string, string][] = [
    ['parse jd', 'haiku 4.5', tailoring || matched ? 'var(--have)' : 'var(--hair)'],
    ['match skills', 'local · 1ms', matched ? 'var(--have)' : tailoring ? 'var(--ink)' : 'var(--hair)'],
    ['tailor', 'sonnet 4.5', done ? 'var(--have)' : tailoring && matched ? 'var(--ink)' : 'var(--hair)'],
    ['honesty lint', 'deterministic', done ? 'var(--have)' : 'var(--hair)'],
    ['render pdf', 'tectonic', downloading === 'resume' ? 'var(--ink)' : 'var(--hair)'],
  ]
  return (
    <div style={{ border: '2px solid var(--ink)' }}>
      {rows.map(([s, meta, col], i) => (
        <div key={s} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', borderBottom: i < rows.length - 1 ? '1px solid var(--rule)' : undefined }}>
          <span style={{ width: 9, height: 9, background: col, flexShrink: 0 }} />
          <span className="ov-micro" style={{ letterSpacing: '0.06em', color: 'var(--ink)', flex: 1 }}>{s}</span>
          <span className="ov-mono" style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--font-mono)' }}>{meta}</span>
        </div>
      ))}
    </div>
  )
}

export type TailorProps = {
  activeJob: ActiveJob; j?: Job; m?: TailorResult['match']; result: TailorResult | null; allFits: number[]
  descLoading: boolean; redFlags: RedFlag[] | null; redFlagsFailed: boolean
  style: 'faithful' | 'aggressive'; setStyle: (s: 'faithful' | 'aggressive') => void; tailoring: boolean; stage: string
  editedResume: string; setEditedResume: (v: string) => void
  coverLetter: string | null; setCoverLetter: (v: string) => void; generatingCl: boolean
  fitting: boolean; downloading: 'resume' | 'cover' | null; setDownloading: (v: 'resume' | 'cover' | null) => void
  onBack: () => void; onTailor: () => void; onFitToPage: () => void; onGenerateCl: () => void
}

export function StageTailor(p: TailorProps) {
  const { activeJob, j, m, result, allFits, descLoading, redFlags, redFlagsFailed } = p
  const have = j?.matched_skills ?? []
  const missing = j?.missing_skills ?? []
  const pageTarget = estimatePageTarget(p.editedResume)

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
      {/* header band */}
      <div style={{ display: 'flex', alignItems: 'stretch', borderBottom: '2px solid var(--ink)', flexWrap: 'wrap' }}>
        <button onClick={p.onBack} className="ov-mono" style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 11, letterSpacing: '0.14em', textTransform: 'uppercase', padding: '0 18px', minHeight: 54, borderRight: '2px solid var(--ink)', background: 'transparent', cursor: 'pointer', color: 'var(--ink)' }}>← results</button>
        <div style={{ padding: '14px 20px', flex: 1, minWidth: 0 }}>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 24, letterSpacing: '-0.02em', color: 'var(--ink)', lineHeight: 1.15 }}>{j?.title ?? 'Pasted job description'}</div>
          {j && <div style={{ marginTop: 4 }}><JobMeta job={j} /></div>}
          {j && (formatSalary(j) || experienceLabel(j)) && (
            <div style={{ marginTop: 8 }}><SalaryLevel job={j} align="left" /></div>
          )}
        </div>
        {j?.url && j.url !== '#' && (
          <a href={j.url} target="_blank" rel="noreferrer" className="ov-mono" style={{ borderLeft: '2px solid var(--ink)', padding: '0 20px', display: 'flex', alignItems: 'center', fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 11, letterSpacing: '0.14em', textTransform: 'uppercase', textDecoration: 'none' }}>original ↗</a>
        )}
      </div>

      <div className="ov-tailorgrid" style={{ flex: 1 }}>
        {/* left column */}
        <div style={{ minWidth: 0, padding: '22px', display: 'flex', flexDirection: 'column', gap: 22 }}>
          {/* skill overlap */}
          {descLoading ? (
            <div className="ov-micro" style={{ fontSize: 9 }}>▸ fetching the full job description…</div>
          ) : (have.length || missing.length) ? (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <span className="ov-micro" style={{ fontSize: 9 }}>skill overlap · deterministic, ~1ms</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <FitBadge fit={j?.fit} allFits={allFits} />
                  <Coverage have={have.length} total={have.length + missing.length} />
                </div>
              </div>
              <Tokens have={have} missing={missing} />
              <p className="ov-micro" style={{ fontSize: 9, marginTop: 10, letterSpacing: '0.06em' }}>filled = already in your cv, verbatim. outlined = wanted but absent, never fabricated.</p>
            </div>
          ) : null}

          {/* legitimacy */}
          <div style={{ border: '2px solid var(--ink)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '11px 14px', background: 'var(--panel)', borderBottom: '1px solid var(--rule)' }}>
              <span className="ov-micro" style={{ fontSize: 9 }}>legitimacy check · advisory, never blocks</span>
              {redFlags && redFlags.length > 0 && <span className="ov-stamp ov-stamp-amber-outline">{redFlags.length} flag{redFlags.length === 1 ? '' : 's'}</span>}
            </div>
            <div style={{ padding: '12px 14px' }}>
              {redFlags === null ? <span className="ov-micro" style={{ fontSize: 9 }}>▸ scanning…</span>
                : redFlagsFailed ? <span style={{ fontSize: 13, color: 'var(--dim)' }}>Couldn't run the check, try again later.</span>
                : redFlags.length === 0 ? <span style={{ fontSize: 13, color: 'var(--have)' }}>No red flags detected.</span>
                : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {redFlags.map((f) => (
                      <div key={f.code} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                        <span className={`ov-stamp ${f.severity === 'high' ? 'ov-stamp-warn' : f.severity === 'warn' ? 'ov-stamp-amber-outline' : 'ov-stamp-info'}`}>{f.severity}</span>
                        <span style={{ fontSize: 13, color: 'var(--body)' }}><b style={{ color: 'var(--ink)' }}>{f.label}</b>{f.evidence ? `, "${f.evidence}"` : ''} <span className="ov-mono" style={{ fontSize: 10, color: 'var(--dim)' }}>· {f.source}</span></span>
                      </div>
                    ))}
                  </div>
                )}
            </div>
          </div>

          {/* tailored result */}
          {result && m && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
              {/* verdict band */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 18, padding: '16px 18px', background: 'var(--ink)', flexWrap: 'wrap' }}>
                <span className="ov-num" style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 30, color: 'var(--paper)' }}>{m.overall_score}<span style={{ fontSize: 14, opacity: 0.6 }}>/100</span></span>
                <span style={{ flex: 1, minWidth: 200, fontSize: 14, lineHeight: 1.5, color: 'var(--paper)' }}>{m.reasoning}</span>
                {/* Only claim a clean lint once it has actually run — during streaming
                    `honesty` is simply not populated yet, which is not the same thing. */}
                {!p.tailoring && result.status === 'completed' && (result.honesty ?? []).length === 0
                  && <span className="ov-stamp ov-stamp-have">honesty ✓</span>}
              </div>

              {/* honesty split */}
              <div className="ov-2col" style={{ border: '2px solid var(--ink)' }}>
                <div className="ov-col-divider" style={{ padding: '16px' }}>
                  <div className="ov-micro" style={{ color: 'var(--have)', fontSize: 9, marginBottom: 10 }}>surfaced from your cv ({m.surfaceable_skills.length}) · honest</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap' }}>
                    {m.surfaceable_skills.map((s) => (
                      <SkillChip key={s} skill={s} tone="have" added={skillInResume(p.editedResume, s)}
                        onToggle={() => p.setEditedResume(patchSkillsLine(p.editedResume, s, skillInResume(p.editedResume, s) ? 'remove' : 'add'))} />
                    ))}
                    {m.surfaceable_skills.length === 0 && <span style={{ fontSize: 12, color: 'var(--dim)' }}>none</span>}
                  </div>
                  <p style={{ fontSize: 12, color: 'var(--body)', marginTop: 10 }}>You have these, they were just buried. Click to drop any.</p>
                </div>
                <div style={{ padding: '16px', background: 'color-mix(in oklab, var(--honesty) 7%, transparent)', borderLeft: '3px solid var(--honesty)' }}>
                  <div className="ov-micro" style={{ color: 'var(--honesty)', fontSize: 9, marginBottom: 10 }}>added for ats, not in your cv ({m.genuine_gaps.filter((s) => skillInResume(p.editedResume, s)).length}) · you must defend these</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap' }}>
                    {m.genuine_gaps.map((s) => (
                      <SkillChip key={s} skill={s} tone="gap" added={skillInResume(p.editedResume, s)}
                        onToggle={() => p.setEditedResume(patchSkillsLine(p.editedResume, s, skillInResume(p.editedResume, s) ? 'remove' : 'add'))} />
                    ))}
                    {m.genuine_gaps.length === 0 && <span style={{ fontSize: 12, color: 'var(--dim)' }}>none</span>}
                  </div>
                  <p style={{ fontSize: 12, color: 'var(--body)', marginTop: 10 }}>Be ready to speak to each in an interview, or click to remove it.</p>
                </div>
              </div>

              {/* honesty lint result */}
              {(result.honesty ?? []).length > 0 && (
                <div style={{ border: '1px solid var(--honesty)', background: 'color-mix(in oklab, var(--honesty) 8%, transparent)', padding: 12 }}>
                  <div className="ov-micro" style={{ color: 'var(--honesty)', fontSize: 9, marginBottom: 6 }}>honesty check · {(result.honesty ?? []).length} to verify</div>
                  {(result.honesty ?? []).map((h, i) => (
                    <p key={i} style={{ fontSize: 12, color: 'var(--body)', marginBottom: 3 }}><span className="ov-chip" style={{ border: '1px solid var(--honesty)', color: 'var(--honesty)' }}>{h.kind}</span> {h.detail}</p>
                  ))}
                </div>
              )}

              {/* pii guardrail readout */}
              <GuardrailPanel report={result.guardrails} />

              {/* export bar */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                <span className="ov-micro" style={{ fontSize: 9 }}>edit before download</span>
                <div style={{ display: 'flex', gap: 8 }}>
                  {pageTarget.underUsedTrailingPage && (
                    <button className="ov-btn" onClick={p.onFitToPage} disabled={p.fitting || p.tailoring}>{p.fitting ? 'fitting…' : `fit to ${pageTarget.targetPages} page${pageTarget.targetPages > 1 ? 's' : ''}`}</button>
                  )}
                  <button className="ov-btn ov-btn-ink" style={{ minWidth: 148, justifyContent: 'center' }} disabled={!p.editedResume.trim() || p.downloading === 'resume'}
                    onClick={async () => {
                      if (!p.editedResume.trim()) return
                      p.setDownloading('resume')
                      try { download(await api.resumePdf(p.editedResume), 'resume.pdf') } catch (e) { toast.error(err(e)) } finally { p.setDownloading(null) }
                    }}>{p.downloading === 'resume' ? 'rendering…' : 'download pdf ↓'}</button>
                </div>
              </div>

              <ResumeWorkspace value={p.editedResume} onChange={p.setEditedResume} showPageBadge label="tailored resume" />

              {/* cover letter */}
              <div style={{ border: '2px solid var(--ink)', padding: 14 }}>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <button className="ov-btn" onClick={p.onGenerateCl} disabled={p.generatingCl || !p.editedResume}>{p.generatingCl ? 'writing…' : p.coverLetter ? 'regenerate cover letter' : 'cover letter'}</button>
                  {p.coverLetter && (
                    <button className="ov-btn" disabled={p.downloading === 'cover'} onClick={async () => {
                      p.setDownloading('cover')
                      try { download(await api.coverLetterPdf(p.coverLetter!), 'cover-letter.pdf') } catch (e) { toast.error(err(e)) } finally { p.setDownloading(null) }
                    }}>{p.downloading === 'cover' ? 'preparing…' : 'download cover pdf ↓'}</button>
                  )}
                </div>
                {p.coverLetter && (
                  <textarea value={p.coverLetter} onChange={(e) => p.setCoverLetter(e.target.value)}
                    style={{ width: '100%', minHeight: 200, marginTop: 12, border: '1px solid var(--rule)', outline: 'none', background: 'var(--surface)', fontFamily: 'var(--font-body)', fontSize: 13, lineHeight: 1.6, padding: 12, color: 'var(--ink)', resize: 'vertical' }} />
                )}
              </div>
            </div>
          )}

          {/* full jd — always open: the column already reserves this space, so
              collapsing it just hides content behind a click and leaves a gap. */}
          <div style={{ border: '1px solid var(--rule)' }}>
            <div className="ov-micro" style={{ padding: '10px 14px', fontSize: 9, borderBottom: '1px solid var(--rule)' }}>full job description</div>
            <p style={{ padding: '4px 14px 14px', fontSize: 13, lineHeight: 1.6, whiteSpace: 'pre-wrap', color: 'var(--body)', maxHeight: 384, overflowY: 'auto' }}>
              {descLoading ? 'Fetching…' : activeJob.jd || 'No description available, try "original ↗".'}
            </p>
          </div>
        </div>

        {/* control rail */}
        <aside className="ov-rail-divider" style={{ borderLeft: '2px solid var(--ink)', minWidth: 0, padding: '22px', display: 'flex', flexDirection: 'column', gap: 18 }}>
          <div className="ov-micro" style={{ fontSize: 9 }}>03 · tailor control</div>

          {/* style */}
          <div>
            <div style={{ display: 'flex', border: '2px solid var(--ink)' }}>
              {STYLES.map((s, i) => (
                <button key={s.key} onClick={() => p.setStyle(s.key)} className="ov-mono"
                  style={{ flex: 1, fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 11, letterSpacing: '0.14em', textTransform: 'uppercase', padding: '13px 10px', cursor: 'pointer', borderRight: i === 0 ? '2px solid var(--ink)' : undefined, background: p.style === s.key ? 'var(--ink)' : 'transparent', color: p.style === s.key ? 'var(--paper)' : 'var(--dim)' }}>{s.key}</button>
              ))}
            </div>
            <p style={{ fontSize: 13, lineHeight: 1.5, color: 'var(--dim)', marginTop: 10 }}>{STYLES.find((s) => s.key === p.style)!.hint}</p>
          </div>

          {/* tailor button */}
          <button className="ov-btn ov-btn-ink" style={{ width: '100%', justifyContent: 'center', padding: 16 }} onClick={p.onTailor} disabled={p.tailoring || descLoading || !activeJob.jd.trim()}>
            {p.tailoring ? 'tailoring…' : descLoading ? 'loading job…' : result ? 're-tailor' : 'tailor my resume'}
          </button>
          {p.tailoring && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ flex: 1 }}><SegmentedBar segments={18} pct={0.5} height={4} color="var(--ink)" /></div>
              <span className="ov-micro" style={{ fontSize: 9 }}>{p.stage}</span>
            </div>
          )}
          <p style={{ fontSize: 12, lineHeight: 1.5, color: 'var(--dim)' }}>Never invents history. Missing JD skills land in your Skills list only, and are flagged so you can strip what you can't back up.</p>

          <Pipeline tailoring={p.tailoring} result={result} downloading={p.downloading} />

          {result && m && m.keyword_missing.length > 0 && (
            <div>
              <div className="ov-micro" style={{ fontSize: 9, marginBottom: 8 }}>keywords wanted, absent ({m.keyword_missing.length})</div>
              <Tokens gap={m.keyword_missing} />
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}
