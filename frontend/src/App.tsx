import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import { Toaster } from '@/components/ui/sonner'
import { api, type Insights, type Job, type RedFlag, type TailorResult } from '@/lib/api'
import { StageBuilder } from '@/components/StageBuilder'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { SegmentedBar } from '@/overlap/SegmentedBar'
import { StageBar } from '@/components/StageBar'
import { FilterRows } from '@/components/SearchFilters'
import { ResultsTable } from '@/components/ResultsTable'
import { PasteJd } from '@/components/PasteJd'
import { ReadoutRail } from '@/components/ReadoutRail'
import { StageTailor } from '@/components/StageTailor'
import { jobKey, jobRank, scoreColor, err } from '@/lib/app-utils'
import type { ActiveJob, View, SavedSearch } from '@/lib/app-types'
import { type ResumeDoc, blankDoc, deserialize, hasContent, serialize, upgradeDoc } from '@/lib/resume-doc'
import { estimatePageTarget } from '@/lib/page-fit'
import { patchSkillsLine } from '@/lib/skills'
import { EMPTY_REFINE, type RefineState } from '@/lib/jobfmt'
import { DEFAULT_FILTERS, toRequestFilters, type FilterState } from '@/lib/search-filters'

const CV_KEY = 'overlap.cv'    // legacy: migrated once into DOC_KEY, then retired
const DOC_KEY = 'overlap.doc'
const SEARCH_KEY = 'overlap.search'

// Load the structured resume: prefer the new doc; migrate a legacy markdown cv once.
function loadDoc(): ResumeDoc {
  try {
    const raw = localStorage.getItem(DOC_KEY)
    if (raw) return upgradeDoc(JSON.parse(raw) as ResumeDoc)
  } catch { /* fall through */ }
  try {
    const legacy = localStorage.getItem(CV_KEY)
    if (legacy) {
      const doc = deserialize(legacy)
      localStorage.setItem(DOC_KEY, JSON.stringify(doc))
      localStorage.removeItem(CV_KEY)
      return doc
    }
  } catch { /* fall through */ }
  return blankDoc()
}



function loadSearch(): SavedSearch {
  try { return JSON.parse(localStorage.getItem(SEARCH_KEY) || '{}') } catch { return {} }
}


function Home() {
  const [doc, setDoc] = useState<ResumeDoc>(() => loadDoc())
  const [uploading, setUploading] = useState(false)
  const hasCv = hasContent(doc)
  const [view, setView] = useState<View>(() => (hasContent(loadDoc()) ? 'search' : 'upload'))

  // Two serializations: search/matching see the FULL master CV (so hiding a
  // section from the printed resume doesn't stop those skills matching jobs);
  // tailoring/rendering see only the enabled subset (what actually prints).
  const cvFull = useMemo(() => (hasCv ? serialize(doc, { include: 'all' }) : ''), [doc, hasCv])
  const cvResume = useMemo(() => (hasCv ? serialize(doc, { include: 'enabled' }) : ''), [doc, hasCv])

  function updateDoc(d: ResumeDoc) {
    setDoc(d)
    try { localStorage.setItem(DOC_KEY, JSON.stringify(d)) } catch { /* quota */ }
  }

  const saved = useRef<SavedSearch>(loadSearch()).current
  const [query, setQuery] = useState(saved.query ?? 'AI Engineer jobs in Singapore')
  const [interpreted, setInterpreted] = useState<Record<string, any> | null>(saved.interpreted ?? null)
  const [jobs, setJobs] = useState<Job[]>(saved.jobs ?? [])
  const [filters, setFilters] = useState<FilterState>(saved.filters ?? DEFAULT_FILTERS)
  const [searching, setSearching] = useState(false)
  const [pending, setPending] = useState<Set<string>>(() => new Set())
  const [refine, setRefine] = useState<RefineState>(EMPTY_REFINE)  // client-side result refinement
  const [strongFitsOnly, setStrongFitsOnly] = useState(false)       // server: gate to good-fit jobs (predictor path)
  const [insights, setInsights] = useState<Insights | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [downloading, setDownloading] = useState<'resume' | 'cover' | null>(null)
  const [progress, setProgress] = useState<{ found: number; target: number; scanned: number; unfetchable?: number } | null>(null)
  const [floor, setFloor] = useState(false)
  const searchAbort = useRef<AbortController | null>(null)
  const enrichAbort = useRef<AbortController | null>(null)
  // Tailoring streams for ~35s. Without this, opening another job and re-tailoring
  // leaves the first stream running: both write the resume box, and the abandoned
  // one throws on navigation and toasts an error over a perfectly good draft.
  const tailorAbort = useRef<AbortController | null>(null)

  const [mode, setMode] = useState<'search' | 'paste'>('search')
  const [jd, setJd] = useState('')
  const [url, setUrl] = useState('')
  const [fetchingUrl, setFetchingUrl] = useState(false)

  // Tailor workspace
  const [activeJob, setActiveJob] = useState<ActiveJob | null>(null)
  const [descLoading, setDescLoading] = useState(false)
  const [redFlags, setRedFlags] = useState<RedFlag[] | null>(null)
  const [redFlagsFailed, setRedFlagsFailed] = useState(false)
  const [style, setStyle] = useState<'faithful' | 'aggressive'>('faithful')
  const [result, setResult] = useState<TailorResult | null>(null)
  const [editedResume, setEditedResume] = useState('')
  const [coverLetter, setCoverLetter] = useState<string | null>(null)
  const [generatingCl, setGeneratingCl] = useState(false)
  const [tailoring, setTailoring] = useState(false)
  const [fitting, setFitting] = useState(false)
  const [stage, setStage] = useState('')

  // Stage is driven by real stream events (see runTailor) — it used to be a timer
  // guessing at progress. Clearing it here keeps the rail tidy when tailoring ends.
  useEffect(() => {
    if (!tailoring) setStage('')
  }, [tailoring])

  // Legitimacy red-flags, deterministic, advisory, auto-fetched whenever a job opens.
  useEffect(() => {
    setRedFlags(null)
    setRedFlagsFailed(false)
    if (!activeJob) return
    const job = activeJob.job
    let ignore = false
    api.redFlags({
      description: job?.description || activeJob.jd || '', company: job?.company ?? '',
      salary_min: job?.salary_min ?? null, salary_max: job?.salary_max ?? null,
      url: job?.url ?? '', posted_date: job?.posted_date ?? '',
    }).then((d) => { if (!ignore) setRedFlags(d.flags) })
      .catch(() => { if (!ignore) { setRedFlags([]); setRedFlagsFailed(true) } })
    return () => { ignore = true }
  }, [activeJob])

  useEffect(() => {
    if (searching) return
    try { localStorage.setItem(SEARCH_KEY, JSON.stringify({ query, interpreted, jobs, filters })) } catch { /* quota */ }
  }, [query, interpreted, jobs, filters, searching])

  useEffect(() => () => { searchAbort.current?.abort(); enrichAbort.current?.abort() }, [])

  type JobPatch = Partial<Job> & { platform: string; external_id: string }
  function patchJob(u: JobPatch) {
    const same = (j: Job) => j.platform === u.platform && j.external_id === u.external_id
    setJobs((prev) => {
      const next = prev.map((j) => (same(j) ? { ...j, ...u } : j))
      return hasCv ? [...next].sort((a, b) => jobRank(b) - jobRank(a)) : next
    })
    setActiveJob((prev) =>
      prev?.job && same(prev.job) ? { job: { ...prev.job, ...u }, jd: u.description ?? prev.jd } : prev,
    )
  }

  async function runEnrich(list: Job[]) {
    const need = list.filter((j) => !j.has_description)
    if (!need.length) return
    enrichAbort.current?.abort()
    const ac = new AbortController()
    enrichAbort.current = ac
    try {
      await api.enrichStream(
        { jobs: need, resume_markdown: cvFull || undefined },
        {
          onUpdate: (u) => {
            patchJob(u)
            setPending((prev) => { const n = new Set(prev); n.delete(jobKey(u)); return n })
          },
          onDone: () => {},
        },
        ac.signal,
      )
    } catch { /* partial keywords are fine, some LinkedIn jobs stay walled */ }
    finally { if (enrichAbort.current === ac) { enrichAbort.current = null; setPending(new Set()) } }
  }

  function resetResult() {
    // Kill any in-flight tailor first: opening a different job while one is streaming
    // would otherwise keep writing the old job's resume into the new job's box.
    tailorAbort.current?.abort()
    tailorAbort.current = null
    setTailoring(false); setFitting(false); setStage('')
    setResult(null); setEditedResume(''); setCoverLetter(null)
  }

  function clearResults() {
    setJobs([]); setInsights(null); setPending(new Set()); setInterpreted(null)
    setProgress(null); setFloor(false); setRefine(EMPTY_REFINE)
    try { localStorage.removeItem(SEARCH_KEY) } catch { /* ignore */ }
  }

  async function onUpload(file: File): Promise<boolean> {
    setUploading(true)
    try {
      const { doc: parsed } = await api.parseResume(file)
      updateDoc(parsed)
      toast.success('Resume parsed into sections, review each one for parsing glitches')
      return true
    } catch (e) { toast.error(err(e)); return false } finally { setUploading(false) }
  }

  function toggleFilter(key: 'experienceLevels' | 'remoteOptions' | 'platforms', value: string) {
    setFilters((f) => {
      const has = f[key].includes(value)
      return { ...f, [key]: has ? f[key].filter((v) => v !== value) : [...f[key], value] }
    })
  }
  function setDate(value: string) { setFilters((f) => ({ ...f, datePosted: value })) }
  function setMax(value: number) { setFilters((f) => ({ ...f, maxJobs: value })) }

  async function onSearch() {
    if (!hasCv) return toast.error('Upload your resume first, then search.')
    if (query.trim().length < 2) return
    searchAbort.current?.abort()
    enrichAbort.current?.abort()
    const ac = new AbortController()
    searchAbort.current = ac
    setSearching(true); setPending(new Set()); setJobs([]); setInterpreted(null); setInsights(null); setRefine(EMPTY_REFINE)
    setProgress(null); setFloor(false)
    const collected: Job[] = []
    try {
      await api.searchStream(
        {
          query,
          resume_markdown: cvFull || undefined,
          filters: toRequestFilters(filters, query, interpreted?.location ?? 'Singapore'),
          strong_fits_only: strongFitsOnly,
        },
        {
          onInterpreted: (d) => { setInterpreted(d) },
          onProgress: (p) => setProgress(p),
          onJob: (j) => {
            const k = jobKey(j)
            if (collected.some((c) => jobKey(c) === k)) return
            collected.push(j)
            if (!j.has_description) setPending((prev) => new Set(prev).add(k))
            setJobs((prev) => {
              const next = [...prev, j]
              return hasCv ? next.sort((a, b) => jobRank(b) - jobRank(a)) : next
            })
          },
          onDone: (fl) => setFloor(!!fl),
        },
        ac.signal,
      )
      if (collected.length === 0) toast.info('No jobs found, try a broader query.')
    } catch (e) {
      if (ac.signal.aborted) return
      if (collected.length > 0) toast.warning(`Connection dropped, showing the ${collected.length} jobs found so far.`)
      else toast.error(err(e))
    } finally {
      if (searchAbort.current === ac) { searchAbort.current = null; setSearching(false) }
    }
    if (!ac.signal.aborted) { onAnalyze(collected); runEnrich(collected) }
  }

  async function onAnalyze(jobsArg?: Job[]) {
    const js = jobsArg ?? jobs
    if (!js.length) return
    setAnalyzing(true)
    try { setInsights(await api.insights({ jobs: js, resume_markdown: cvFull || undefined })) }
    catch { /* best-effort */ } finally { setAnalyzing(false) }
  }

  async function openJob(job: Job) {
    resetResult()
    setActiveJob({ job, jd: job.description || '' })
    setView('job')
    if (!job.has_description) {
      setDescLoading(true)
      try {
        const d = await api.jobDescription({
          platform: job.platform, external_id: job.external_id, url: job.url,
          title: job.title, resume_markdown: cvFull || undefined,
        })
        if (d.has_description) {
          patchJob({
            platform: job.platform, external_id: job.external_id,
            description: d.description, has_description: true,
            matched_skills: d.matched_skills, missing_skills: d.missing_skills,
            relevance: d.relevance, ...(d.fit != null ? { fit: d.fit } : {}),
          })
        }
      } catch { /* leave description empty */ }
      finally { setDescLoading(false); setPending((prev) => { const n = new Set(prev); n.delete(jobKey(job)); return n }) }
    }
  }

  function openPasteJd() {
    if (!hasCv) return toast.error('Upload your resume first.')
    if (jd.trim().length < 20) return toast.error('Paste a longer job description.')
    resetResult()
    setActiveJob({ jd })
    setView('job')
  }

  function applySkillAdditions(md: string, match: { surfaceable_skills: string[]; genuine_gaps: string[] }): string {
    let out = md
    for (const s of [...match.surfaceable_skills, ...match.genuine_gaps]) out = patchSkillsLine(out, s, 'add')
    return out
  }

  async function runTailor(jdText: string) {
    if (!hasCv) return toast.error('Upload your resume first.')
    if (jdText.trim().length < 20) return toast.error('This posting has no description to tailor against.')
    tailorAbort.current?.abort()
    const ac = new AbortController()
    tailorAbort.current = ac
    setTailoring(true)
    setStage('reading the posting')
    setResult(null)
    setEditedResume('')
    setCoverLetter(null)
    const previous = editedResume
    let acc = ''
    try {
      await api.tailorStream({ jd_text: jdText, resume_markdown: cvResume, style }, {
        onMatch: (match) => {
          if (ac.signal.aborted) return
          setStage('drafting · streaming')
          // Paint the score and skill rail before any text arrives. Advisory panels
          // that depend on the finished draft (honesty, guardrails) stay empty until
          // `done` — see the honesty stamp's `!tailoring` guard.
          setResult({
            tailored_resume_markdown: null, cover_letter_text: null, cover_letter_word_count: null,
            match, changes_made: [], keywords_added: [], status: 'tailoring', errors: [],
          })
        },
        onDelta: (text) => { if (ac.signal.aborted) return; acc += text; setEditedResume(acc) },
        onDone: (d) => {
          if (ac.signal.aborted) return
          setStage('honesty lint · checking every claim')
          setResult({
            tailored_resume_markdown: d.tailored_resume_markdown, cover_letter_text: null,
            cover_letter_word_count: null, match: d.match, changes_made: [], keywords_added: [],
            status: 'completed', errors: [], honesty: d.honesty, guardrails: d.guardrails,
          })
          // Adopt the server's authoritative text, not the accumulated deltas: the PII
          // guard can force-restore the contact header at the end of the stream.
          setEditedResume(applySkillAdditions(d.tailored_resume_markdown, d.match))
        },
      }, ac.signal)
    } catch (e) {
      if (ac.signal.aborted) return  // superseded by a newer tailor — not an error
      setEditedResume(previous)  // a failed re-tailor must not discard the existing draft
      toast.error(err(e))
    } finally { if (tailorAbort.current === ac) { tailorAbort.current = null; setTailoring(false) } }
  }

  async function onFitToPage() {
    if (!activeJob || !editedResume.trim()) return
    const t = estimatePageTarget(editedResume)
    if (!t.underUsedTrailingPage) return
    tailorAbort.current?.abort()
    const ac = new AbortController()
    tailorAbort.current = ac
    setFitting(true)
    setCoverLetter(null)
    const previous = editedResume
    let acc = ''
    try {
      await api.tailorStream(
        { jd_text: activeJob.jd, resume_markdown: previous, style, target_pages: t.targetPages },
        {
          onDelta: (text) => { if (ac.signal.aborted) return; acc += text; setEditedResume(acc) },
          onDone: (d) => {
            if (ac.signal.aborted) return
            setResult((r) => ({
              tailored_resume_markdown: d.tailored_resume_markdown, cover_letter_text: null,
              cover_letter_word_count: null, match: d.match, changes_made: [], keywords_added: [],
              status: 'completed', errors: [], honesty: d.honesty,
              guardrails: d.guardrails ?? r?.guardrails ?? null,
            }))
            setEditedResume(applySkillAdditions(d.tailored_resume_markdown, d.match))
          },
        },
        ac.signal,
      )
    } catch (e) {
      if (ac.signal.aborted) return  // superseded — not an error
      setEditedResume(previous)  // a failed refit must not leave a half-streamed draft
      toast.error(err(e))
    } finally { if (tailorAbort.current === ac) { tailorAbort.current = null; setFitting(false) } }
  }

  async function onGenerateCl() {
    if (!editedResume || !activeJob) return
    setGeneratingCl(true)
    try {
      const cl = await api.coverLetter({ jd_text: activeJob.jd, resume_markdown: editedResume })
      setCoverLetter(cl.cover_letter_text)
    } catch (e) { toast.error(err(e)) } finally { setGeneratingCl(false) }
  }

  async function onFetchUrl() {
    if (!url.trim()) return
    setFetchingUrl(true)
    try {
      const { jd_text } = await api.extractJd({ url })
      setJd(jd_text)
      toast.success('Job description extracted, review it, then Tailor.')
    } catch (e) { toast.error(err(e)) } finally { setFetchingUrl(false) }
  }

  const m = result?.match
  const j = activeJob?.job
  const allFits = jobs.map((job) => job.fit).filter((f): f is number => f != null)

  const goStage = (v: View) => {
    if (v === 'search' && !hasCv) return toast.error('Upload your resume first.')
    if (v === 'job' && !activeJob) return
    setView(v)
  }

  return (
    <div className="ov" style={{ minHeight: '100%' }}>
      <div className="ov-shell" style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
        <StageBar view={view} cv={hasCv} hasJob={!!activeJob} onGo={goStage} />

        {view === 'upload' && (
          <StageBuilder doc={doc} setDoc={updateDoc} uploading={uploading} onUpload={onUpload} onTailor={() => goStage('search')} />
        )}

        {view === 'search' && (
          <div className="ov-searchgrid" style={{ flex: 1 }}>
            <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column' }}>
              {/* mode tabs */}
              <div style={{ display: 'flex', borderBottom: '2px solid var(--ink)' }}>
                {(['search', 'paste'] as const).map((mo) => (
                  <button key={mo} onClick={() => setMode(mo)} className="ov-mono"
                    style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 11, letterSpacing: '0.14em', textTransform: 'uppercase', padding: '13px 18px', cursor: 'pointer', borderRight: '2px solid var(--ink)', background: mode === mo ? 'var(--ink)' : 'transparent', color: mode === mo ? 'var(--paper)' : 'var(--dim)' }}>
                    {mo === 'search' ? 'search boards' : 'paste jd'}
                  </button>
                ))}
                <span className="ov-micro" style={{ marginLeft: 'auto', alignSelf: 'center', padding: '0 16px', fontSize: 9 }}>step 02 / 03</span>
              </div>

              {mode === 'search' ? (
                <div>
                  {/* query line */}
                  <div style={{ display: 'flex', borderBottom: '2px solid var(--ink)' }}>
                    <input value={query} onChange={(e) => setQuery(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && onSearch()}
                      placeholder='e.g. "50 remote AI Engineer jobs on JobStreet, this week"'
                      style={{ flex: 1, minWidth: 0, border: 'none', outline: 'none', background: 'transparent', fontFamily: 'var(--font-mono)', fontSize: 15, padding: '16px 20px', color: 'var(--ink)' }} />
                    <button onClick={onSearch} disabled={searching}
                      style={{ borderLeft: '2px solid var(--ink)', background: searching ? 'var(--honesty)' : 'var(--ink)', color: 'var(--paper)', fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 12, letterSpacing: '0.16em', textTransform: 'uppercase', padding: '0 26px', cursor: 'pointer' }}>
                      {searching ? 'searching…' : 'execute'}
                    </button>
                  </div>

                  {/* strong-fits gate toggle — off by default (explore everything, ranked by
                      fit); on gates to good AI-fit jobs. Effective only with the predictor on. */}
                  <button onClick={() => setStrongFitsOnly((v) => !v)} aria-pressed={strongFitsOnly}
                    style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '9px 20px', borderBottom: '2px solid var(--ink)', background: 'transparent', cursor: 'pointer', textAlign: 'left', flexWrap: 'wrap' }}>
                    <span style={{ width: 13, height: 13, flexShrink: 0, border: '1.5px solid var(--ink)', background: strongFitsOnly ? 'var(--ink)' : 'transparent', color: 'var(--paper)', fontSize: 9, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>{strongFitsOnly ? '✓' : ''}</span>
                    <span className="ov-micro" style={{ fontSize: 9, color: 'var(--ink)' }}>only strong fits</span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--dim)' }}>off = explore every match, ranked by AI fit · on = good fits only</span>
                  </button>

                  {/* scan strip while searching */}
                  {searching && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 20px', background: 'var(--panel)', borderBottom: '2px solid var(--ink)' }}>
                      <span className="ov-micro" style={{ fontSize: 9, flexShrink: 0 }}>
                        {progress ? `${progress.found} of ${progress.target} good fit · ${progress.scanned} scanned` : `scraping three boards · ${jobs.length} found`}
                      </span>
                      <div style={{ flex: 1 }}>
                        <SegmentedBar segments={40} pct={progress ? progress.found / Math.max(1, progress.target) : Math.min(0.6, jobs.length / 25)} height={8} color="var(--ink)" />
                      </div>
                    </div>
                  )}

                  <FilterRows filters={filters} setDate={setDate} setMax={setMax} toggleFilter={toggleFilter} />

                  {/* scoring progress after search */}
                  {!searching && pending.size > 0 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 20px', borderBottom: '1px solid var(--rule)' }}>
                      <span className="ov-micro" style={{ fontSize: 9, flexShrink: 0 }}>scoring · {jobs.length - pending.size} of {jobs.length} ready</span>
                      <div style={{ flex: 1 }}><SegmentedBar segments={40} pct={jobs.length ? (jobs.length - pending.size) / jobs.length : 0} height={8} color="var(--ink)" /></div>
                    </div>
                  )}

                  {floor && !searching && (
                    <div className="ov-micro" style={{ color: 'var(--honesty)', padding: '10px 20px', borderBottom: '1px solid var(--rule)' }}>
                      fewer than {progress?.target ?? 'N'} strong matches; showing the closest.
                    </div>
                  )}

                  {jobs.length > 0 && (
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 20px', background: 'var(--panel)', borderBottom: '1px solid var(--rule)' }}>
                      <span className="ov-micro" style={{ fontSize: 9 }}>{jobs.length} result{jobs.length === 1 ? '' : 's'}</span>
                      <button onClick={clearResults} className="ov-micro" style={{ fontSize: 9, background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--dim)' }}>clear ✕</button>
                    </div>
                  )}

                  {/* results table */}
                  <ResultsTable jobs={jobs} pending={pending} allFits={allFits} onOpen={openJob} refine={refine} setRefine={setRefine} />
                </div>
              ) : (
                <PasteJd url={url} setUrl={setUrl} jd={jd} setJd={setJd} fetchingUrl={fetchingUrl} onFetchUrl={onFetchUrl} onTailor={openPasteJd} tailoring={tailoring} />
              )}
            </div>

            {/* readout rail */}
            <ReadoutRail insights={insights} analyzing={analyzing} scoreColor={scoreColor} className="ov-rail-divider" />
          </div>
        )}

        {view === 'job' && activeJob && (
          <StageTailor
            activeJob={activeJob} j={j} m={m} result={result} allFits={allFits}
            descLoading={descLoading} redFlags={redFlags} redFlagsFailed={redFlagsFailed}
            style={style} setStyle={setStyle} tailoring={tailoring} stage={stage}
            editedResume={editedResume} setEditedResume={setEditedResume}
            coverLetter={coverLetter} setCoverLetter={setCoverLetter} generatingCl={generatingCl}
            fitting={fitting} downloading={downloading} setDownloading={setDownloading}
            onBack={() => goStage('search')} onTailor={() => runTailor(activeJob.jd)}
            onFitToPage={onFitToPage} onGenerateCl={onGenerateCl}
          />
        )}

        <footer style={{ padding: '18px 22px', borderTop: '2px solid var(--ink)', marginTop: 'auto' }}>
          <span className="ov-micro" style={{ fontSize: 9 }}>overlap · a portfolio project · no account · cv never stored</span>
        </footer>
      </div>
    </div>
  )
}


export default function App() {
  return (
    <>
      <ErrorBoundary>
        <Home />
      </ErrorBoundary>
      <Toaster richColors position="top-right" />
    </>
  )
}
