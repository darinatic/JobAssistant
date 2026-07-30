import { useEffect, useRef, useState } from 'react'
import { SegmentedBar } from './SegmentedBar'

/* Section 04 — resume & cover letter. The DOWNLOAD PDF button runs the app's real
   2800ms render sequence (synthetic here, but the substep labels match what the
   renderer actually does). Its completion turns the pipeline's `render pdf` dot
   green — the two are one linked state, so they live in one component. */

const DL_STEPS = [
  { at: 0, label: 'collecting content' },
  { at: 300, label: 'honesty lint · final pass' },
  { at: 650, label: 'typesetting · latex pass 1 of 2' },
  { at: 1500, label: 'typesetting · latex pass 2 of 2' },
  { at: 2200, label: 'embedding fonts' },
  { at: 2560, label: 'writing resume_govtech.pdf' },
]
const DL_TOTAL = 2800

const PIPELINE = [
  { stage: 'parse jd', meta: 'haiku 4.5' },
  { stage: 'match skills', meta: 'local · 1ms' },
  { stage: 'tailor', meta: 'sonnet 4.5' },
  { stage: 'honesty lint', meta: 'deterministic' },
  { stage: 'render pdf', meta: 'tectonic' },
]

type Status = 'idle' | 'running' | 'done'

function Dot({ color }: { color: string }) {
  return <span style={{ width: 9, height: 9, background: color, flexShrink: 0, display: 'inline-block' }} />
}

function ResumeSheet() {
  const roles: [string, string, string][] = [
    ['ML Engineer · Fictional Labs', '2024 — Now', 'Shipped a RAG assistant serving 40k monthly queries; cut hallucination rate with a deterministic grounding check.'],
    ['Data Science Intern · Sample Co', '2023', 'Built an SBERT + PEFT reranker; +18% top-3 retrieval accuracy on an internal eval set.'],
  ]
  return (
    <div style={{ background: '#fff', border: '1px solid oklch(0.15 0.01 250 / 0.3)', padding: 28, maxWidth: 430, color: '#000', fontSize: 11, lineHeight: 1.4 }}>
      <div style={{ textAlign: 'center', fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 18 }}>Ng Tzun May</div>
      <div style={{ textAlign: 'center', fontSize: 9.5, marginTop: 4, color: '#222' }}>
        tzunmay@example.com · +65 8000 0000 · github.com/tzunmay · Singapore
      </div>
      {(['Summary', 'Experience', 'Skills'] as const).map((section) => (
        <div key={section} style={{ marginTop: 14 }}>
          <div style={{ textTransform: 'uppercase', fontWeight: 700, fontSize: 11.5, borderBottom: '1px solid rgb(0 0 0 / 0.65)', paddingBottom: 2 }}>{section}</div>
          {section === 'Summary' && (
            <p style={{ marginTop: 6 }}>AI/ML engineer focused on production LLM systems — retrieval, evaluation, and honest tooling. Comfortable from data pipeline to deployed endpoint.</p>
          )}
          {section === 'Experience' && (
            <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 8 }}>
              {roles.map(([r, date, desc]) => (
                <div key={r}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 600 }}>
                    <span>{r}</span><span>{date}</span>
                  </div>
                  <ul style={{ margin: '3px 0 0', paddingLeft: 17 }}><li>{desc}</li></ul>
                </div>
              ))}
            </div>
          )}
          {section === 'Skills' && (
            <p style={{ marginTop: 6 }}>Python, PyTorch, RAG, SBERT, PEFT, multi-agent eval, AWS, vector search, FastAPI, Docker</p>
          )}
        </div>
      ))}
    </div>
  )
}

export function ResumeSection() {
  const [status, setStatus] = useState<Status>('idle')
  const [t, setT] = useState(0)
  const timers = useRef<number[]>([])

  useEffect(() => () => timers.current.forEach(clearTimeout), [])

  const run = () => {
    if (status === 'running') return
    setStatus('running')
    setT(0)
    const started = performance.now()
    const id = window.setInterval(() => {
      const elapsed = performance.now() - started
      if (elapsed >= DL_TOTAL) {
        window.clearInterval(id)
        setT(DL_TOTAL)
        setStatus('done')
        const revert = window.setTimeout(() => setStatus('idle'), 5000)
        timers.current.push(revert)
      } else {
        setT(elapsed)
      }
    }, 60)
    timers.current.push(id)
  }

  const pct = Math.min(t / DL_TOTAL, 1)
  const step = [...DL_STEPS].reverse().find((s) => t >= s.at) ?? DL_STEPS[0]
  const renderDone = status === 'done'
  const btnLabel = status === 'idle' ? 'download pdf ↓' : status === 'done' ? 'saved ✓' : `rendering… ${Math.round(pct * 100)}%`

  return (
    <section style={{ borderBottom: '2px solid var(--ink)' }}>
      <div style={{ padding: '16px 44px', borderBottom: '1px solid var(--rule)' }}>
        <div className="ov-eyebrow">04 · resume & cover letter</div>
      </div>
      <div className="ov-2col">
        {/* left: copy + pipeline */}
        <div className="ov-col-divider ov-pad">
          <h2 className="ov-h2" style={{ fontSize: 38, lineHeight: 1.08, maxWidth: 460 }}>Edit it, then take the PDF.</h2>
          <p className="ov-copy" style={{ marginTop: 20 }}>
            Two styles: <b>faithful</b> reorders and rephrases and cuts nothing; <b>aggressive</b> restructures hard for one
            page. Edit the markdown beside a live page render, generate a cover letter from the same evidence, then export
            through LaTeX — which narrates its own passes as it runs.
          </p>
          <div style={{ marginTop: 28, border: '2px solid var(--ink)' }}>
            {PIPELINE.map((p, i) => {
              const isRender = p.stage === 'render pdf'
              const color = isRender ? (renderDone ? 'var(--have)' : 'var(--hair)') : 'var(--have)'
              return (
                <div key={p.stage} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '11px 14px', borderBottom: i < PIPELINE.length - 1 ? '1px solid var(--rule)' : undefined }}>
                  <Dot color={color} />
                  <span className="ov-micro" style={{ letterSpacing: '0.06em', color: 'var(--ink)', flex: 1 }}>{p.stage}</span>
                  <span className="ov-mono" style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--font-mono)' }}>{p.meta}</span>
                </div>
              )
            })}
          </div>
        </div>

        {/* right: export bar + progress + sheet */}
        <div style={{ padding: '26px', background: 'var(--panel)', display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
            <span className="ov-micro" style={{ fontSize: 9 }}>tailored resume · edit before download</span>
            <button
              onClick={run}
              disabled={status === 'running'}
              className="ov-mono"
              style={{
                fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 11, letterSpacing: '0.12em', textTransform: 'uppercase',
                minWidth: 152, padding: '9px 14px', cursor: status === 'running' ? 'progress' : 'pointer',
                border: status === 'running' ? '2px dashed var(--ink)' : '2px solid var(--ink)',
                background: status === 'done' ? 'var(--have)' : status === 'running' ? 'transparent' : 'var(--ink)',
                color: status === 'running' ? 'var(--ink)' : 'var(--paper)',
              }}
            >
              {btnLabel}
            </button>
          </div>

          {status !== 'idle' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '9px 12px', background: renderDone ? 'color-mix(in oklab, var(--have) 10%, transparent)' : 'color-mix(in oklab, var(--ink) 5%, transparent)' }}>
              <span className="ov-micro" style={{ fontSize: 9, width: 150, flexShrink: 0, color: 'var(--ink)' }}>
                {renderDone ? 'resume_govtech.pdf · 1 page · 84 kb · saved' : step.label}
              </span>
              <div style={{ flex: 1 }}>
                <SegmentedBar segments={48} pct={pct} height={8} color={renderDone ? 'var(--have)' : 'var(--ink)'} live={!renderDone} />
              </div>
            </div>
          )}

          <ResumeSheet />
        </div>
      </div>
    </section>
  )
}
