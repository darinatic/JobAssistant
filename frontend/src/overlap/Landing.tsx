import { useNavigate } from 'react-router-dom'
import './overlap.css'
import { HeroDemo } from './HeroDemo'
import { HonestySplit } from './HonestySplit'
import { ResumeSection } from './ResumeSection'
import { SegmentedBar } from './SegmentedBar'

/* Marketing landing at `/`. Product page + portfolio evidence in one: the hero is
   a live looping replica of the app's scraping panel, and the closing sections
   explain the engineering rather than shouting adjectives. Pre-launch — no metrics,
   logos, or testimonials anywhere. Design language shared with the app redesign. */

function Eyebrow({ children, color }: { children: React.ReactNode; color?: string }) {
  return <div className="ov-eyebrow" style={{ color, marginBottom: 16 }}>{children}</div>
}

function StatCell({ num, label }: { num: string; label: string }) {
  return (
    <div style={{ padding: '14px 16px', flex: 1 }}>
      <div className="ov-num" style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 24, lineHeight: 1, color: 'var(--ink)' }}>{num}</div>
      <div className="ov-micro" style={{ fontSize: 9, marginTop: 6 }}>{label}</div>
    </div>
  )
}

export default function Landing() {
  const navigate = useNavigate()
  const openApp = () => navigate('/app')

  return (
    <div className="ov">
      <div className="ov-shell">
        {/* ---- sticky top bar ---- */}
        <header style={{ position: 'sticky', top: 0, zIndex: 20, display: 'flex', alignItems: 'stretch', background: 'var(--surface)', borderBottom: '2px solid var(--ink)' }}>
          <a href="/" style={{ background: 'var(--ink)', color: 'var(--paper)', fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 15, letterSpacing: '0.02em', padding: '14px 18px', textDecoration: 'none', display: 'flex', alignItems: 'center' }}>OVERLAP</a>
          <nav className="ov-hide-sm" style={{ display: 'flex', alignItems: 'center', gap: 26, padding: '0 24px' }}>
            {[['#speed', 'concurrency'], ['#honesty', 'honesty'], ['#build', 'how it\'s built']].map(([href, label]) => (
              <a key={href} href={href} className="ov-micro" style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.14em', textDecoration: 'none' }}>{label}</a>
            ))}
          </nav>
          <div className="ov-micro" style={{ display: 'flex', alignItems: 'center', padding: '0 18px', marginLeft: 'auto', borderLeft: '1px solid var(--rule)', fontSize: 9 }}>pre-launch</div>
          <button className="ov-btn ov-btn-ink" style={{ border: 'none' }} onClick={openApp}>upload your cv →</button>
        </header>

        {/* ---- hero ---- */}
        <section className="ov-hero" style={{ borderBottom: '2px solid var(--ink)' }}>
          <div className="ov-col-divider ov-pad" style={{ paddingTop: 56, paddingBottom: 48 }}>
            <Eyebrow>singapore · three boards · nothing stored</Eyebrow>
            <h1 className="ov-h1">Three boards at once. A resume that stays honest.</h1>
            <p className="ov-lead" style={{ marginTop: 22 }}>
              Search MyCareersFuture, LinkedIn and JobStreet in one go. Every posting is scored against your own CV in about
              a millisecond — no model, no guessing. Then tailor a resume that never invents a line of your history.
            </p>
            <div style={{ display: 'flex', gap: 12, marginTop: 28, flexWrap: 'wrap' }}>
              <button className="ov-btn ov-btn-ink" onClick={openApp}>upload your cv →</button>
              <a className="ov-btn" href="#speed">how it works ↓</a>
            </div>
            <div style={{ display: 'flex', border: '2px solid var(--ink)', marginTop: 32 }}>
              <StatCell num="3" label="boards, concurrent" />
              <div style={{ borderLeft: '1px solid var(--rule)', display: 'flex', flex: 2 }}>
                <StatCell num="~1ms" label="match, no llm" />
                <div style={{ borderLeft: '1px solid var(--rule)', display: 'flex', flex: 1 }}>
                  <StatCell num="0" label="bytes on our servers" />
                </div>
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <HeroDemo />
          </div>
        </section>

        {/* ---- stage strip (ink) ---- */}
        <section className="ov-3col" style={{ background: 'var(--ink)', borderBottom: '2px solid var(--ink)' }}>
          {[
            ['01 resume', 'Drop in your CV. It is parsed in your browser and held in localStorage — never uploaded.'],
            ['02 search', 'Ask in plain language. Three boards are fetched at once and every posting is scored against your words.'],
            ['03 tailor', 'Pick a posting. Get a tailored resume and cover letter, with every added claim labelled.'],
          ].map(([tag, body], i) => (
            <div key={tag} style={{ padding: '24px 22px', borderRight: i < 2 ? '1px solid oklch(0.97 0 0 / 0.2)' : undefined }}>
              <div className="ov-micro" style={{ color: 'var(--paper)', opacity: 0.6, marginBottom: 10 }}>{tag}</div>
              <p style={{ fontSize: 15, lineHeight: 1.5, color: 'var(--paper)', opacity: 0.92 }}>{body}</p>
            </div>
          ))}
        </section>

        {/* ---- 01 concurrency ---- */}
        <section id="speed" className="ov-2col" style={{ scrollMarginTop: 70, borderBottom: '2px solid var(--ink)' }}>
          <div className="ov-col-divider ov-pad">
            <Eyebrow>01 · concurrency</Eyebrow>
            <h2 className="ov-h2">One search. Three boards. Wall clock equals the slowest one.</h2>
            <p className="ov-copy" style={{ marginTop: 20 }}>
              MyCareersFuture answers through its API with the full job description. LinkedIn arrives as cards, then
              backfills each posting. JobStreet needs a headless browser to get past its wall.
            </p>
            <p className="ov-copy">
              They run in parallel and stream in as they land, so a fast board never waits behind a slow one. The total
              time is the slowest board, not the sum.
            </p>
          </div>
          <div className="ov-pad" style={{ display: 'flex', flexDirection: 'column' }}>
            {[
              ['MyCareersFuture', '3.1s', 'var(--have)', 'API, full JD inline — no detail fetch.'],
              ['LinkedIn', '4.4s', 'var(--ink)', 'Cards first, then a polite per-posting backfill.'],
              ['JobStreet', '6.2s', 'var(--gap)', 'Headless browser render — the slow board, and it says so.'],
            ].map(([name, time, color, note], i) => (
              <div key={name} style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '16px 0', borderBottom: i < 3 ? '1px solid var(--rule)' : undefined }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                  <span className="ov-mono" style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 12, color: 'var(--ink)' }}>{name}</span>
                  <span className="ov-mono ov-num" style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 15, color: color as string }}>{time}</span>
                </div>
                <span style={{ fontSize: 14, color: 'var(--body)' }}>{note}</span>
              </div>
            ))}
            <div className="ov-micro" style={{ marginTop: 16, fontSize: 10 }}>no board is hidden behind a single combined progress bar.</div>
          </div>
        </section>

        {/* ---- 02 matching (reversed) ---- */}
        <section className="ov-2col ov-reverse" style={{ borderBottom: '2px solid var(--ink)' }}>
          {/* demo left */}
          <div className="ov-order-demo ov-col-divider ov-pad" style={{ background: 'var(--panel)', display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* skill overlap card */}
            <div style={{ border: '2px solid var(--ink)', background: 'var(--surface)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '11px 14px', borderBottom: '1px solid var(--rule)' }}>
                <span className="ov-micro" style={{ fontSize: 9 }}>skill overlap · deterministic</span>
                <span className="ov-stamp ov-stamp-have">7 / 9</span>
              </div>
              <div style={{ padding: '14px' }}>
                <div style={{ display: 'flex', flexWrap: 'wrap', marginBottom: 12 }}>
                  {['Python', 'PyTorch', 'RAG', 'SBERT', 'AWS', 'FastAPI', 'Docker'].map((s) => <span key={s} className="ov-chip ov-chip-have">{s}</span>)}
                  {['Kubernetes', 'Airflow'].map((s) => <span key={s} className="ov-chip ov-chip-gap">{s}</span>)}
                </div>
                <SegmentedBar segments={9} pct={7 / 9} height={11} color="var(--have)" live={false} />
                <div className="ov-micro" style={{ fontSize: 9, marginTop: 10 }}>filled = in your cv, verbatim / outlined = wanted, absent</div>
              </div>
            </div>
            {/* demand vs you card */}
            <div style={{ border: '2px solid var(--ink)', background: 'var(--surface)', padding: '14px' }}>
              <div className="ov-micro" style={{ fontSize: 9, marginBottom: 12 }}>demand vs you</div>
              {[
                ['python', 92, true], ['llm / rag', 78, true], ['mlops', 64, false],
                ['kubernetes', 58, false], ['pytorch', 51, true], ['airflow', 44, false],
              ].map(([label, pct, have]) => (
                <div key={label as string} style={{ display: 'grid', gridTemplateColumns: '96px 1fr 34px', alignItems: 'center', gap: 10, marginBottom: 7 }}>
                  <span className="ov-mono" style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--dim)' }}>{label}</span>
                  <div style={{ display: 'flex', height: 8, background: 'var(--hair)' }}>
                    <div style={{ width: `${pct}%`, background: (have as boolean) ? 'var(--have)' : 'var(--gap)' }} />
                  </div>
                  <span className="ov-mono ov-num" style={{ fontFamily: 'var(--font-mono)', fontSize: 11, textAlign: 'right', color: 'var(--dim)' }}>{pct}%</span>
                </div>
              ))}
              <div className="ov-micro" style={{ fontSize: 9, marginTop: 10, letterSpacing: '0.08em' }}>amber is what the market keeps asking for and you cannot yet claim. that is your study list.</div>
            </div>
          </div>
          {/* text right */}
          <div className="ov-order-text ov-pad">
            <Eyebrow>02 · matching</Eyebrow>
            <h2 className="ov-h2">Scored against your own words, not a model's opinion.</h2>
            <p className="ov-copy" style={{ marginTop: 20 }}>
              Matching is a local gazetteer, not an API call. It runs in about a millisecond, costs nothing, and returns the
              exact same answer every time — so the ranking is reproducible and cheap enough to run on every result.
            </p>
            <p className="ov-copy">
              Filled chips are skills already in your CV, verbatim. Outlined chips are what the posting wants and you do not
              have yet. Nothing is inferred or softened.
            </p>
          </div>
        </section>

        {/* ---- 03 honesty split ---- */}
        <HonestySplit />

        {/* ---- 04 resume & cover letter ---- */}
        <ResumeSection />

        {/* ---- 05 legitimacy ---- */}
        <section className="ov-2col" style={{ borderBottom: '2px solid var(--ink)' }}>
          <div className="ov-col-divider ov-pad">
            <Eyebrow color="var(--gap)">05 · legitimacy check</Eyebrow>
            <h2 className="ov-h2">It tells you when a posting smells wrong.</h2>
            <p className="ov-copy" style={{ marginTop: 20 }}>
              Ghost listings, unlicensed recruiters, month-old reposts — checked against MOM licensing rules and known
              ghost-listing patterns. The triggering line is quoted and the authority named.
            </p>
            <p className="ov-copy"><b>Advisory only.</b> It flags; it never blocks you from applying.</p>
          </div>
          <div className="ov-pad" style={{ display: 'flex', alignItems: 'flex-start' }}>
            <div style={{ border: '2px solid var(--ink)', width: '100%' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '11px 14px', background: 'color-mix(in oklab, var(--ink) 5%, transparent)', borderBottom: '1px solid var(--rule)' }}>
                <span className="ov-micro" style={{ fontSize: 9 }}>legitimacy check · advisory</span>
                <span className="ov-stamp ov-stamp-amber-outline">2 flags</span>
              </div>
              {[
                ['warn', 'Unverified recruiter', '"WhatsApp me directly to apply"', 'MOM'],
                ['info', 'Stale posting', 'reposted 34 days, still open', 'FTC'],
              ].map(([sev, label, quote, src]) => (
                <div key={label} style={{ display: 'grid', gridTemplateColumns: '76px 1fr 74px', alignItems: 'center', borderBottom: '1px solid oklch(0.15 0.01 250 / 0.12)' }}>
                  <div style={{ padding: '12px' }}>
                    <span className={`ov-stamp ov-stamp-${sev === 'warn' ? 'warn' : 'info'}`}>{sev}</span>
                  </div>
                  <div style={{ padding: '12px' }}>
                    <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink)' }}>{label}</div>
                    <div className="ov-mono" style={{ fontSize: 11, color: 'var(--dim)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>{quote}</div>
                  </div>
                  <div className="ov-micro" style={{ fontSize: 9, padding: '12px', textAlign: 'right' }}>{src}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ---- 06 how it's built ---- */}
        <section id="build" style={{ scrollMarginTop: 70, borderBottom: '2px solid var(--ink)' }}>
          <div style={{ padding: '52px 44px 32px' }}>
            <Eyebrow>06 · how it's built</Eyebrow>
            <h2 className="ov-h2" style={{ fontSize: 38, maxWidth: 820, lineHeight: 1.08 }}>Three decisions the whole product rests on.</h2>
          </div>
          <div className="ov-3col" style={{ borderTop: '1px solid var(--rule)' }}>
            {[
              ['concurrency', 'Boards run in parallel, and say so.', 'A single combined bar would have hidden that two boards finished in three seconds.'],
              ['determinism', 'Matching never touches a model.', 'Local, ~1ms, identical answers — cheap enough to run on every result.'],
              ['honesty', 'The seam is shown, not hidden.', 'A deterministic lint separates CV-sourced from ATS-added, and every added claim stays one click from deletion.'],
            ].map(([tag, title, body], i) => (
              <div key={tag} style={{ padding: '28px 24px', borderRight: i < 2 ? '1px solid var(--rule)' : undefined }}>
                <div className="ov-micro" style={{ fontSize: 10, marginBottom: 12 }}>{tag}</div>
                <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 21, letterSpacing: '-0.02em', lineHeight: 1.2, color: 'var(--ink)' }}>{title}</div>
                <p style={{ fontSize: 15, lineHeight: 1.55, color: 'var(--body)', marginTop: 12 }}>{body}</p>
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', borderTop: '1px solid var(--rule)' }}>
            {['react', 'typescript', 'vite', 'tailwind', 'fastapi', 'playwright', 'claude haiku + sonnet', 'latex / tectonic', 'localstorage only'].map((s, i) => (
              <span key={s} className="ov-micro" style={{ fontSize: 10, padding: '11px 16px', borderRight: i < 8 ? '1px solid var(--rule)' : undefined }}>{s}</span>
            ))}
          </div>
        </section>

        {/* ---- CTA (ink) ---- */}
        <section id="try" style={{ scrollMarginTop: 70, background: 'var(--ink)', padding: '64px 44px', borderBottom: '2px solid var(--ink)' }}>
          <div className="ov-eyebrow" style={{ color: 'var(--paper)', opacity: 0.6, marginBottom: 16 }}>pre-launch · your cv never leaves your browser</div>
          <h2 className="ov-h2" style={{ color: 'var(--paper)', fontSize: 52, letterSpacing: '-0.035em', lineHeight: 1.0, maxWidth: 760 }}>Drop in your CV. See what actually matches.</h2>
          <p style={{ fontSize: 17, lineHeight: 1.6, color: 'var(--paper)', opacity: 0.85, maxWidth: 520, marginTop: 20 }}>
            No account, nothing stored on a server, no resume sent to a third party. It runs in your browser and scores
            against your own words.
          </p>
          <div style={{ display: 'flex', gap: 12, marginTop: 28, flexWrap: 'wrap' }}>
            <button className="ov-btn ov-btn-paper" onClick={openApp}>upload your cv →</button>
            <a className="ov-btn" href="https://github.com/darinatic/JobAssistant" target="_blank" rel="noreferrer" style={{ color: 'var(--paper)', borderColor: 'oklch(0.97 0 0 / 0.4)' }}>read the source</a>
          </div>
        </section>

        {/* ---- footer ---- */}
        <footer style={{ padding: '20px 44px', display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span className="ov-micro" style={{ fontSize: 9 }}>overlap · built in singapore · open source</span>
          <span className="ov-micro" style={{ fontSize: 9 }}>mycareersfuture · linkedin · jobstreet</span>
        </footer>
      </div>
    </div>
  )
}
