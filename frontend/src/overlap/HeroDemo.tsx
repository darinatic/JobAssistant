import { useEffect, useRef, useState } from 'react'
import { SegmentedBar } from './SegmentedBar'

/* The hero image IS the product: a working replica of the app's scraping panel,
   looping. Three boards fetch concurrently and finish on their OWN clocks — that
   disagreement is the whole argument, so the gauges never share a progress value.
   One ~60ms ticker drives a clock `t` that wraps every 8600ms (6.4s of activity
   then a ~2.2s hold on the finished state). All values derive from `t` at render. */

const CYCLE = 8600
const ACTIVE = 6400

type Board = {
  key: string
  name: string
  short: string
  total: number
  finish: number
  running: string
  done: string
  color: string
}

const BOARDS: Board[] = [
  { key: 'mcf', name: 'MyCareersFuture', short: 'MCF', total: 18, finish: 3100, running: 'api · fetching jd', done: 'complete · full jd', color: 'var(--have)' },
  { key: 'li', name: 'LinkedIn', short: 'LI', total: 13, finish: 4400, running: 'cards · paging', done: 'cards · backfilled', color: 'var(--ink)' },
  { key: 'js', name: 'JobStreet', short: 'JS', total: 4, finish: 6200, running: 'browser · rendering', done: 'browser · 6.2s', color: 'var(--gap)' },
]

type Row = {
  n: string
  title: string
  company: string
  platform: string
  cover: string
  verdict: 'top fit' | 'strong' | 'moderate'
  appearAt: number
  amber?: boolean
}

const ROWS: Row[] = [
  { n: '01', title: 'AI Engineer, LLM Platform', company: 'GovTech', platform: 'mcf', cover: '7/9', verdict: 'top fit', appearAt: 1500 },
  { n: '02', title: 'ML Engineer (NLP)', company: 'Shopee', platform: 'linkedin', cover: '6/10', verdict: 'strong', appearAt: 2900 },
  { n: '03', title: 'Senior Data Scientist, Risk', company: 'DBS Bank', platform: 'jobstreet', cover: '4/9', verdict: 'moderate', appearAt: 5100, amber: true },
]

const REDUCED = () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(REDUCED)
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const on = () => setReduced(mq.matches) // event handler, not synchronous in the effect body
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  return reduced
}

export function HeroDemo() {
  const reduced = usePrefersReducedMotion()
  const [t, setT] = useState(0)
  const [playing, setPlaying] = useState(!REDUCED())
  const visible = useRef(true)
  const rootRef = useRef<HTMLDivElement>(null)

  // Pause the loop when off-screen; the ticker guards on this ref.
  useEffect(() => {
    if (reduced) return
    const el = rootRef.current
    if (!el) return
    const io = new IntersectionObserver(([e]) => { visible.current = e.isIntersecting }, { threshold: 0.15 })
    io.observe(el)
    return () => io.disconnect()
  }, [reduced])

  useEffect(() => {
    if (reduced || !playing) return
    const id = window.setInterval(() => {
      if (visible.current) setT((prev) => (prev + 60) % CYCLE)
    }, 60)
    return () => window.clearInterval(id)
  }, [playing, reduced])

  // Reduced-motion renders the FINISHED state (not a frozen mid-run) — derive the
  // display clock rather than syncing it into state from an effect.
  const clock = reduced ? ACTIVE + 200 : t
  const finished = clock >= ACTIVE
  const scanPct = Math.min(clock / ACTIVE, 1)
  const scanLabel = clock < 320 ? 'opening three boards' : clock < 4400 ? 'fetching concurrently' : 'jobstreet still rendering'
  const scanPctText = `${Math.round(scanPct * 100)}%`

  return (
    <div ref={rootRef} style={{ display: 'flex', flexDirection: 'column', background: 'var(--surface)' }}>
      {/* header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '11px 14px', borderBottom: '2px solid var(--ink)' }}>
        <span className="ov-micro" style={{ animation: playing ? 'ov-tick 1.1s ease-in-out infinite' : undefined }}>
          live · scraping three boards
        </span>
        <button
          className="ov-micro"
          aria-label={playing ? 'Pause the demo' : 'Play the demo'}
          onClick={() => setPlaying((p) => !p)}
          style={{ border: '1px solid var(--rule)', background: 'transparent', padding: '4px 8px', cursor: 'pointer', color: 'var(--ink)' }}
        >
          {playing ? 'pause ▮▮' : 'play ▶'}
        </button>
      </div>

      {/* scan strip */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '10px 14px', background: 'var(--panel)', borderBottom: '2px solid var(--ink)' }}>
        <span className="ov-micro" style={{ width: 132, flexShrink: 0, letterSpacing: '0.1em' }}>{scanLabel}</span>
        <div style={{ flex: 1 }}>
          <SegmentedBar segments={40} pct={scanPct} height={9} color="var(--ink)" live={!finished} />
        </div>
        <span className="ov-mono ov-num" style={{ width: 44, textAlign: 'right', fontSize: 11, fontWeight: 700, color: 'var(--ink)', fontFamily: 'var(--font-mono)' }}>
          {scanPctText}
        </span>
      </div>

      {/* three gauges */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', borderBottom: '2px solid var(--ink)' }}>
        {BOARDS.map((b, i) => {
          const p = Math.min(clock / b.finish, 1)
          const queued = clock < 320
          const done = clock >= b.finish
          const count = Math.round(p * b.total)
          const elapsed = (Math.min(clock, b.finish) / 1000).toFixed(1)
          const status = queued ? 'queued' : done ? b.done : b.running
          return (
            <div key={b.key} style={{ padding: '14px 14px', borderRight: i < 2 ? '1px solid var(--rule)' : undefined, display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span className="ov-micro" style={{ fontSize: 9 }}>{b.name}</span>
                <span className="ov-mono ov-num" style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--font-mono)' }}>{elapsed}s</span>
              </div>
              <div className="ov-num" style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 32, lineHeight: 1, color: b.key === 'js' ? 'var(--gap)' : 'var(--ink)' }}>
                {count}
              </div>
              <SegmentedBar segments={6} pct={p} height={11} color={b.color} live={!done && !queued} />
              <span className="ov-micro" style={{ fontSize: 10, letterSpacing: '0.1em', animation: !done && !queued && playing ? 'ov-tick 1.1s ease-in-out infinite' : undefined, color: done ? 'var(--have)' : 'var(--dim)' }}>
                {status}
              </span>
            </div>
          )
        })}
      </div>

      {/* result table */}
      <div>
        <div style={{ display: 'grid', gridTemplateColumns: '40px 1fr 92px', background: 'var(--panel)', borderBottom: '1px solid var(--rule)' }}>
          {['#', 'role', 'verdict'].map((h) => (
            <span key={h} className="ov-micro" style={{ fontSize: 9, padding: '7px 12px' }}>{h}</span>
          ))}
        </div>
        {ROWS.map((r) => {
          const shown = finished || clock >= r.appearAt
          if (!shown) return null
          const age = clock - r.appearAt
          const flashing = !finished && age >= 0 && age < 700
          return (
            <div
              key={r.n}
              style={{
                display: 'grid',
                gridTemplateColumns: '40px 1fr 92px',
                borderBottom: '1px solid var(--rule)',
                alignItems: 'center',
                animation: flashing ? 'ov-rise 0.3s ease-out both' : undefined,
                background: flashing ? 'color-mix(in oklab, var(--have) 10%, transparent)' : 'transparent',
                transition: 'background 0.5s linear',
              }}
            >
              <span className="ov-mono ov-num" style={{ fontSize: 12, color: 'var(--dim)', padding: '12px 12px', fontFamily: 'var(--font-mono)' }}>{r.n}</span>
              <div style={{ padding: '10px 12px', minWidth: 0 }}>
                <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 16, letterSpacing: '-0.015em', color: 'var(--ink)', lineHeight: 1.2 }}>{r.title}</div>
                <div className="ov-mono" style={{ fontSize: 11, color: 'var(--dim)', fontFamily: 'var(--font-mono)', marginTop: 3, letterSpacing: '0.02em' }}>
                  {r.company} · {r.platform} · <span className="ov-num">{r.cover}</span>
                </div>
              </div>
              <div style={{ padding: '10px 12px' }}>
                <span className={`ov-stamp ov-stamp-${r.verdict === 'top fit' ? 'topfit' : r.verdict}`}>{r.verdict}</span>
              </div>
            </div>
          )
        })}

        {/* shimmer skeleton holding the next slot while the run is active */}
        {!finished && clock <= 6600 && (
          <div style={{ display: 'grid', gridTemplateColumns: '40px 1fr 92px', borderBottom: '1px solid var(--rule)', alignItems: 'center', opacity: 0.9 }}>
            <span className="ov-mono" style={{ fontSize: 12, color: 'var(--hair)', padding: '12px 12px', fontFamily: 'var(--font-mono)' }}>··</span>
            <div style={{ padding: '12px 12px', display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div style={{ height: 9, width: '54%', background: 'var(--hair)', animation: 'ov-tick 1.1s ease-in-out infinite' }} />
              <div style={{ height: 9, width: '32%', background: 'var(--hair)', animation: 'ov-tick 1.1s ease-in-out infinite' }} />
            </div>
            <span className="ov-micro" style={{ fontSize: 9, padding: '10px 12px', animation: 'ov-tick 1.1s ease-in-out infinite' }}>scoring…</span>
          </div>
        )}
      </div>
    </div>
  )
}
