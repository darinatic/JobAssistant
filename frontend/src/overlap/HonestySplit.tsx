import { useState } from 'react'

/* Section 03 — the centerpiece. Two panes: skills SURFACED from the CV (honest,
   green) vs ADDED FOR ATS (rose, "you must defend these"). Every rose chip is a
   toggle; the ink footer sentence rewrites itself from how many are still active.
   Letting a visitor disarm the tool's own additions and watch the guarantee
   update is the point of the section. */

const SURFACED = ['PyTorch', 'RAG pipelines', 'Multi-agent', 'SBERT / PEFT', 'AWS', 'Vector search']
const ADDED = ['Kubernetes', 'Airflow']

const GUARANTEE: Record<number, string> = {
  0: 'Nothing added that you cannot back up. This resume says only what your CV already says.',
  1: 'One keyword added for the ATS, flagged and removable. Your experience section is untouched.',
  2: 'Two keywords added for the ATS, both flagged and removable. Your experience section is untouched.',
}

function Chip({ label, active, tone, onToggle }: { label: string; active: boolean; tone: 'have' | 'honesty'; onToggle: () => void }) {
  const color = tone === 'have' ? 'var(--have)' : 'var(--honesty)'
  return (
    <button
      aria-pressed={active}
      onClick={onToggle}
      style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 13,
        padding: '5px 10px',
        margin: '0 4px 4px 0',
        cursor: 'pointer',
        whiteSpace: 'nowrap',
        border: active ? `1px solid ${color}` : '1px dashed var(--rule)',
        background: active ? color : 'transparent',
        color: active ? 'var(--paper)' : 'var(--dim)',
        transition: 'background 0.12s linear, color 0.12s linear',
      }}
      title={active ? `Remove ${label}` : `Add ${label} back`}
    >
      {label}{active ? '  ×' : '  +'}
    </button>
  )
}

export function HonestySplit() {
  const [surfaced, setSurfaced] = useState<Record<string, boolean>>(() => Object.fromEntries(SURFACED.map((s) => [s, true])))
  const [added, setAdded] = useState<Record<string, boolean>>(() => Object.fromEntries(ADDED.map((s) => [s, true])))
  const activeAdded = ADDED.filter((s) => added[s]).length
  const activeSurfaced = SURFACED.filter((s) => surfaced[s]).length

  return (
    <section id="honesty" style={{ borderBottom: '2px solid var(--ink)' }}>
      {/* intro */}
      <div style={{ padding: '52px 44px 32px' }}>
        <div className="ov-eyebrow" style={{ color: 'var(--honesty)', marginBottom: 16 }}>03 · the honesty split</div>
        <h2 className="ov-h2" style={{ fontSize: 46, letterSpacing: '-0.03em', lineHeight: 1.03, maxWidth: 900 }}>
          A tailored resume that never invents your history.
        </h2>
        <p className="ov-lead" style={{ marginTop: 20, maxWidth: 640 }}>
          Other tools will write you a past you did not have. Overlap adds missing keywords to your skills list only, and
          shows the seam — so you always know which claims are yours and which you would have to defend.
        </p>
      </div>

      {/* two panes */}
      <div className="ov-2col" style={{ borderTop: '2px solid var(--ink)' }}>
        <div className="ov-col-divider" style={{ padding: '22px 24px' }}>
          <div className="ov-micro" style={{ color: 'var(--have)', marginBottom: 14 }}>
            surfaced from your cv ({activeSurfaced}) · honest
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap' }}>
            {SURFACED.map((s) => (
              <Chip key={s} label={s} active={!!surfaced[s]} tone="have" onToggle={() => setSurfaced((p) => ({ ...p, [s]: !p[s] }))} />
            ))}
          </div>
          <p style={{ fontSize: 14, lineHeight: 1.55, color: 'var(--body)', marginTop: 14, maxWidth: 420 }}>
            You already have these — they were just buried three bullets deep. Reordering is not lying.
          </p>
        </div>

        <div style={{ padding: '22px 24px', background: 'color-mix(in oklab, var(--honesty) 7%, transparent)', borderLeft: '3px solid var(--honesty)' }}>
          <div className="ov-micro" style={{ color: 'var(--honesty)', marginBottom: 14 }}>
            added for ats, not in your cv ({activeAdded}) · you must defend these
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap' }}>
            {ADDED.map((s) => (
              <Chip key={s} label={s} active={!!added[s]} tone="honesty" onToggle={() => setAdded((p) => ({ ...p, [s]: !p[s] }))} />
            ))}
          </div>
          <p style={{ fontSize: 14, lineHeight: 1.55, color: 'var(--body)', marginTop: 14, maxWidth: 420 }}>
            Keyword-only, never written into your experience. Click any of them to strip it out — try it.
          </p>
        </div>
      </div>

      {/* rewriting guarantee footer */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 18, padding: '20px 24px', background: 'var(--ink)', borderTop: '2px solid var(--ink)' }}>
        <span className="ov-stamp ov-stamp-have" style={{ flexShrink: 0 }}>honesty ✓</span>
        <span style={{ fontFamily: 'var(--font-body)', fontSize: 15, lineHeight: 1.5, color: 'var(--paper)' }}>
          {GUARANTEE[activeAdded] ?? GUARANTEE[2]}
        </span>
      </div>
    </section>
  )
}
