// Extracted from App.tsx (pure move, no behaviour change).
import type { GuardrailReport, Job } from '@/lib/api'
import { fitLabel } from '@/lib/fit'
import { SegmentedBar } from '@/overlap/SegmentedBar'
import { formatSalary, salaryFull, postedLabel, experienceLabel } from '@/lib/jobfmt'

// ---- industrial primitives -------------------------------------------------

export function Chip({ label, tone = 'gap' }: { label: string; tone?: 'have' | 'gap' | 'honesty' }) {
  if (tone === 'have') return <span className="ov-chip ov-chip-have">{label}</span>
  if (tone === 'honesty') return <span className="ov-chip" style={{ border: '1px solid var(--honesty)', color: 'var(--honesty)' }}>{label}</span>
  return <span className="ov-chip ov-chip-gap">{label}</span>
}

export function Tokens({ have = [], gap = [], missing = [], honesty = [] }: { have?: string[]; gap?: string[]; missing?: string[]; honesty?: string[] }) {
  if (!have.length && !gap.length && !missing.length && !honesty.length)
    return <span style={{ fontSize: 13, color: 'var(--dim)' }}>none</span>
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap' }}>
      {have.map((s) => <Chip key={s} label={s} tone="have" />)}
      {gap.map((s) => <Chip key={s} label={s} tone="gap" />)}
      {honesty.map((s) => <Chip key={s} label={s} tone="honesty" />)}
      {missing.map((s) => <Chip key={s} label={s} tone="gap" />)}
    </div>
  )
}

// A toggleable skill chip. green = surfaceable (you have it), rose = genuine gap.
export function SkillChip({ skill, tone, added, onToggle }: {
  skill: string; tone: 'have' | 'gap'; added: boolean; onToggle: () => void
}) {
  const color = tone === 'have' ? 'var(--have)' : 'var(--honesty)'
  return (
    <button
      aria-pressed={added}
      onClick={onToggle}
      style={{
        fontFamily: 'var(--font-mono)', fontSize: 12, padding: '4px 9px', margin: '0 4px 4px 0', cursor: 'pointer', whiteSpace: 'nowrap',
        border: added ? `1px solid ${color}` : '1px dashed var(--rule)',
        background: added ? color : 'transparent',
        color: added ? 'var(--paper)' : 'var(--dim)',
      }}
      title={added ? 'Click to remove' : 'Click to add'}
    >
      {skill}{added ? '  ×' : '  +'}
    </button>
  )
}

export const PII_LABEL: Record<string, string> = {
  NAME: 'name', EMAIL: 'email', PHONE: 'phone', URL: 'profile links',
}

// PII guardrail readout — what was stripped from the CV before it reached the AI,
// and whether every identifier was restored locally afterward.
export function GuardrailPanel({ report }: { report?: GuardrailReport | null }) {
  if (!report) return null
  if (!report.available) {
    return (
      <div style={{ border: '1px solid var(--honesty)', background: 'color-mix(in oklab, var(--honesty) 8%, transparent)', padding: 12 }}>
        <div className="ov-micro" style={{ color: 'var(--honesty)', fontSize: 9 }}>pii guardrail unavailable</div>
        <p style={{ fontSize: 12, color: 'var(--body)', marginTop: 4 }}>Tailored on your full CV this time — redaction couldn't run.</p>
      </div>
    )
  }
  const parts = Object.entries(report.redaction.counts).map(([k, n]) => `${PII_LABEL[k] ?? k.toLowerCase()} ×${n}`)
  const accent = report.header_forced ? 'var(--honesty)' : 'var(--have)'
  return (
    <div style={{ border: `1px solid ${accent}`, background: `color-mix(in oklab, ${accent} 7%, transparent)`, padding: 12 }}>
      <div className="ov-micro" style={{ color: accent, fontSize: 9, marginBottom: 6 }}>
        ▸ pii guardrail · {report.redaction.total} identifier{report.redaction.total === 1 ? '' : 's'} stripped before the ai
      </div>
      <p style={{ fontSize: 12, color: 'var(--body)', marginBottom: 4 }}>
        Removed before sending: {parts.length ? parts.join(' · ') : 'none found'}. The AI tailored an anonymized copy; your details were restored locally.
      </p>
      <p style={{ fontSize: 11, color: report.header_forced ? 'var(--honesty)' : 'var(--dim)' }}>
        {report.header_forced
          ? '⚠ a token did not round-trip — your contact header was restored from your CV.'
          : '✓ all identifiers restored locally.'}
      </p>
    </div>
  )
}

export function Coverage({ have, total }: { have: number; total: number }) {
  const pct = total ? have / total : 0
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }} title={`${have} of ${total} skills matched`}>
      <span className="ov-num" style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 700, color: 'var(--ink)' }}>{have}/{total}</span>
      <div style={{ width: 60 }}><SegmentedBar segments={9} pct={pct} height={8} live={false} /></div>
    </div>
  )
}

// Relative fit within the current results, never the raw score.
export function FitBadge({ fit, allFits }: { fit?: number; allFits: number[] }) {
  if (fit == null) return null
  const l = fitLabel(fit, allFits).label.toLowerCase()
  // Short stamps (per the design) so a "moderate fit" can't overflow the fixed
  // verdict column into the readout rail. Keep "top fit" as the marker.
  const [stampClass, text] = l.includes('top') ? ['ov-stamp-topfit', 'top fit']
    : l.includes('strong') ? ['ov-stamp-strong', 'strong']
    : l.includes('moderate') ? ['ov-stamp-moderate', 'moderate']
    : ['ov-stamp-moderate', 'weak']
  return <span className={`ov-stamp ${stampClass}`} title="AI-predicted fit, relative to these results">{text}</span>
}

export function JobMeta({ job }: { job: Job }) {
  const posted = postedLabel(job)
  return (
    <span className="ov-mono" style={{ fontSize: 11, fontFamily: 'var(--font-mono)', letterSpacing: '0.03em', color: 'var(--dim)' }}>
      <span style={{ color: 'var(--ink)' }}>{job.company}</span>
      {'  ·  '}<span style={{ color: 'var(--geo)' }}>◍ {job.location || 'Singapore'}</span>
      {'  ·  '}{job.platform}
      {posted && <>{'  ·  '}{posted}</>}
    </span>
  )
}

// Salary (ink mono, tabular) over a small seniority stamp — the right-aligned
// readout column of a job row / the tailor header. Null when neither is disclosed.
export function SalaryLevel({ job, align = 'right' }: { job: Job; align?: 'right' | 'left' }) {
  const salary = formatSalary(job)
  const level = experienceLabel(job)
  if (!salary && !level) return null
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5, alignItems: align === 'right' ? 'flex-end' : 'flex-start' }}>
      {salary && (
        <span className="ov-num" title={salaryFull(job) ?? undefined} style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 700, color: 'var(--ink)', whiteSpace: 'nowrap' }}>{salary}</span>
      )}
      {level && (
        <span className="ov-stamp ov-stamp-info" title={job.experience_raw ?? undefined} style={{ fontSize: 9 }}>{level}</span>
      )}
    </div>
  )
}
