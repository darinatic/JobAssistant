import { Component, type ReactNode, useEffect, useRef, useState } from 'react'
import { ThemeProvider } from 'next-themes'
import { toast } from 'sonner'
import { Toaster } from '@/components/ui/sonner'
import { ThemeToggle } from '@/components/ThemeToggle'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { api, ApiError, type Insights, type Job, type RedFlag, type TailorResult } from '@/lib/api'
import { ResumeEditor } from '@/components/ResumeEditor'
import { estimatePageTarget } from '@/lib/page-fit'
import { fitLabel } from '@/lib/fit'

const CV_KEY = 'overlap.cv'
const SEARCH_KEY = 'overlap.search'

type ActiveJob = { job?: Job; jd: string }

const STYLES = [
  { key: 'faithful' as const, hint: 'Keep everything — reorder and rephrase only. Safest.' },
  { key: 'balanced' as const, hint: 'Condense weak content and drop the irrelevant. Aims for one page.' },
  { key: 'aggressive' as const, hint: 'Restructure, cut low-relevance sections, hard one page. Max fit.' },
]
type SavedSearch = { query?: string; interpreted?: Record<string, any> | null; jobs?: Job[] }

function loadSearch(): SavedSearch {
  try { return JSON.parse(localStorage.getItem(SEARCH_KEY) || '{}') } catch { return {} }
}

function scoreColor(s: number): string {
  if (s >= 80) return 'text-have'
  if (s >= 60) return 'text-primary'
  if (s >= 40) return 'text-gap'
  return 'text-honesty'
}

function err(e: unknown): string {
  if (e instanceof ApiError) return e.message
  const msg = e instanceof Error ? e.message : String(e)
  // fetch() throws a bare TypeError when it can't reach the host.
  if (/failed to fetch|networkerror|load failed|err_connection/i.test(msg))
    return "Can't reach the server — make sure the backend is running, then try again."
  return msg
}

function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function Tokens({ have = [], gap = [], missing = [], honesty = [] }: { have?: string[]; gap?: string[]; missing?: string[]; honesty?: string[] }) {
  if (!have.length && !gap.length && !missing.length && !honesty.length)
    return <span className="text-sm text-muted-foreground">—</span>
  return (
    <div className="flex flex-wrap gap-1.5">
      {have.map((s) => <span key={s} className="tok tok-have">{s}</span>)}
      {gap.map((s) => <span key={s} className="tok tok-gap">{s}</span>)}
      {honesty.map((s) => <span key={s} className="tok tok-honesty">{s}</span>)}
      {missing.map((s) => <span key={s} className="tok">{s}</span>)}
    </div>
  )
}

function Coverage({ have, total }: { have: number; total: number }) {
  const pct = total ? Math.round((100 * have) / total) : 0
  return (
    <div className="hidden sm:flex items-center gap-2" title={`${have} of ${total} skills matched`}>
      <span className="font-mono text-xs tabular-nums text-muted-foreground">{have}/{total}</span>
      <div className="h-1.5 w-14 rounded-full bg-muted overflow-hidden">
        <div className="h-full rounded-full bg-have" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

// Relative fit within the current results — never the raw score (it's compressed
// and misleads out of 100). `allFits` is every fit value in the batch for ranking.
function FitBadge({ fit, allFits }: { fit?: number; allFits: number[] }) {
  if (fit == null) return null
  const { label, color } = fitLabel(fit, allFits)
  return (
    <span className="font-mono text-xs font-semibold" style={{ color }}
      title="AI-predicted fit, relative to these results">{label}</span>
  )
}

function Spinner({ label, className = '' }: { label?: string; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs text-muted-foreground ${className}`}>
      <span className="inline-block size-3 shrink-0 rounded-full border-2 border-muted border-t-primary animate-spin" aria-hidden />
      {label}
    </span>
  )
}

function JobMeta({ job, size = 'sm' }: { job: Job; size?: 'sm' | 'lg' }) {
  return (
    <div className={size === 'lg' ? 'space-y-1' : 'space-y-0.5'}>
      <p className={`font-medium text-foreground truncate ${size === 'lg' ? 'text-base' : 'text-sm'}`}>{job.company}</p>
      <p className="flex items-center gap-1.5 font-mono text-xs truncate" style={{ color: 'var(--loc)' }}>
        <span aria-hidden>◍</span>{job.location || 'Singapore'}
      </p>
      <span className="eyebrow">{job.platform}</span>
    </div>
  )
}

function StepHead({ n, title, hint }: { n: string; title: string; hint?: string }) {
  return (
    <div className="mb-5 flex items-baseline gap-3">
      <span className="eyebrow tabular-nums">{n}</span>
      <h2 className="display text-lg font-semibold">{title}</h2>
      {hint && <span className="ml-auto eyebrow">{hint}</span>}
    </div>
  )
}

function Home() {
  const [cv, setCv] = useState<string>(() => localStorage.getItem(CV_KEY) || '')
  const [uploading, setUploading] = useState(false)
  const [cvOpen, setCvOpen] = useState(false)

  function updateCv(md: string) {
    setCv(md)
    try { localStorage.setItem(CV_KEY, md) } catch { /* quota */ }
  }

  const saved = useRef<SavedSearch>(loadSearch()).current
  const [query, setQuery] = useState(saved.query ?? 'AI Engineer jobs in Singapore')
  const [interpreted, setInterpreted] = useState<Record<string, any> | null>(saved.interpreted ?? null)
  const [jobs, setJobs] = useState<Job[]>(saved.jobs ?? [])
  const [searching, setSearching] = useState(false)
  const [enriching, setEnriching] = useState(0)   // # of cards still backfilling keywords
  const [insights, setInsights] = useState<Insights | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const searchAbort = useRef<AbortController | null>(null)
  const enrichAbort = useRef<AbortController | null>(null)

  const [jd, setJd] = useState('')
  const [url, setUrl] = useState('')
  const [fetchingUrl, setFetchingUrl] = useState(false)

  // Drawer + tailor workspace
  const [activeJob, setActiveJob] = useState<ActiveJob | null>(null)
  const [descLoading, setDescLoading] = useState(false)
  const [redFlags, setRedFlags] = useState<RedFlag[] | null>(null)
  const [redFlagsFailed, setRedFlagsFailed] = useState(false)
  const [style, setStyle] = useState<'faithful' | 'balanced' | 'aggressive'>('faithful')
  const [result, setResult] = useState<TailorResult | null>(null)
  const [editedResume, setEditedResume] = useState('')
  const [coverLetter, setCoverLetter] = useState<string | null>(null)
  const [generatingCl, setGeneratingCl] = useState(false)
  const [tailoring, setTailoring] = useState(false)
  const [fitting, setFitting] = useState(false)
  const [stage, setStage] = useState('')

  useEffect(() => {
    if (!tailoring) { setStage(''); return }
    const stages = ['Parsing the job description…', 'Matching your skills…', 'Tailoring your resume…', 'Formatting the resume…']
    let i = 0
    setStage(stages[0])
    const id = setInterval(() => { i = Math.min(i + 1, stages.length - 1); setStage(stages[i]) }, 3500)
    return () => clearInterval(id)
  }, [tailoring])

  // Esc closes the drawer.
  useEffect(() => {
    if (!activeJob) return
    const h = (e: KeyboardEvent) => e.key === 'Escape' && setActiveJob(null)
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [activeJob])

  // Legitimacy red-flags — deterministic, advisory, auto-fetched whenever the drawer
  // opens (or is patched with a fuller description once it loads).
  useEffect(() => {
    // This effect also re-fires on patchJob updates for the SAME job (new activeJob
    // object, same identity — e.g. once the on-demand description finishes loading),
    // which is fine: red flags legitimately refetch against the fuller description.
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

  // Persist the search (query + results) so a refresh restores them instead of
  // losing everything. Skip writing while a search is streaming in.
  useEffect(() => {
    if (searching) return
    try { localStorage.setItem(SEARCH_KEY, JSON.stringify({ query, interpreted, jobs })) } catch { /* quota */ }
  }, [query, interpreted, jobs, searching])

  // Abort any in-flight streams when the page unmounts (refresh/navigate).
  useEffect(() => () => { searchAbort.current?.abort(); enrichAbort.current?.abort() }, [])

  type JobPatch = Partial<Job> & { platform: string; external_id: string }
  // Patch one job by (platform, external_id) — updates the listing card AND the open
  // drawer if it's the same job. Re-sorts by relevance when a CV is present.
  function patchJob(u: JobPatch) {
    const same = (j: Job) => j.platform === u.platform && j.external_id === u.external_id
    setJobs((prev) => {
      const next = prev.map((j) => (same(j) ? { ...j, ...u } : j))
      return cv ? [...next].sort((a, b) => (b.fit ?? b.relevance ?? 0) - (a.fit ?? a.relevance ?? 0)) : next
    })
    setActiveJob((prev) =>
      prev?.job && same(prev.job) ? { job: { ...prev.job, ...u }, jd: u.description ?? prev.jd } : prev,
    )
  }

  // Background keyword backfill — after search paints cards, fetch the descriptions
  // that came back empty (LinkedIn/JobStreet) and patch each card as it arrives.
  async function runEnrich(list: Job[]) {
    const need = list.filter((j) => !j.has_description)
    if (!need.length) return
    enrichAbort.current?.abort()
    const ac = new AbortController()
    enrichAbort.current = ac
    setEnriching(need.length)
    try {
      await api.enrichStream(
        { jobs: need, resume_markdown: cv || undefined },
        { onUpdate: (u) => { patchJob(u); setEnriching((n) => Math.max(0, n - 1)) }, onDone: () => {} },
        ac.signal,
      )
    } catch { /* partial keywords are fine — some LinkedIn jobs stay walled */ }
    finally { if (enrichAbort.current === ac) { enrichAbort.current = null; setEnriching(0) } }
  }

  function resetResult() { setResult(null); setEditedResume(''); setCoverLetter(null) }

  async function onUpload(file: File) {
    setUploading(true)
    try {
      const { markdown, chars } = await api.parseResume(file)
      updateCv(markdown)
      toast.success(`Resume loaded (${chars.toLocaleString()} chars) — review the markdown for parsing glitches`)
    } catch (e) { toast.error(err(e)) } finally { setUploading(false) }
  }

  async function onSearch() {
    if (query.trim().length < 2) return
    searchAbort.current?.abort()          // supersede any in-flight search
    enrichAbort.current?.abort()          // and its background keyword backfill
    const ac = new AbortController()
    searchAbort.current = ac
    setSearching(true); setEnriching(0); setJobs([]); setInterpreted(null); setInsights(null)
    const collected: Job[] = []
    try {
      await api.searchStream(
        { query, resume_markdown: cv || undefined },
        {
          onInterpreted: (d) => setInterpreted(d),
          onJob: (j) => {
            collected.push(j)
            setJobs((prev) => {
              const next = [...prev, j]
              return cv ? next.sort((a, b) => (b.fit ?? b.relevance ?? 0) - (a.fit ?? a.relevance ?? 0)) : next
            })
          },
          onDone: () => {},
        },
        ac.signal,
      )
      if (collected.length === 0) toast.info('No jobs found — try a broader query.')
    } catch (e) {
      if (ac.signal.aborted) return       // cancelled/superseded — stay quiet
      // Keep whatever streamed in before the drop; just tell the user.
      if (collected.length > 0) toast.warning(`Connection dropped — showing the ${collected.length} jobs found so far.`)
      else toast.error(err(e))
    } finally {
      if (searchAbort.current === ac) { searchAbort.current = null; setSearching(false) }
    }
    // Search done — backfill the missing keywords in the background (not awaited).
    if (!ac.signal.aborted) runEnrich(collected)
  }

  async function onAnalyze() {
    setAnalyzing(true)
    try { setInsights(await api.insights({ jobs, resume_markdown: cv || undefined })) }
    catch (e) { toast.error(err(e)) } finally { setAnalyzing(false) }
  }

  async function openJob(job: Job) {
    resetResult()
    setActiveJob({ job, jd: job.description || '' })
    // Search returns LinkedIn/JobStreet cards without descriptions (kept fast +
    // avoids LinkedIn's burst wall). Fetch this one's description on demand now.
    if (!job.has_description) {
      setDescLoading(true)
      try {
        const d = await api.jobDescription({
          platform: job.platform, external_id: job.external_id, url: job.url,
          resume_markdown: cv || undefined,
        })
        if (d.has_description) {
          // patchJob updates BOTH the drawer and the underlying listing card.
          patchJob({
            platform: job.platform, external_id: job.external_id,
            description: d.description, has_description: true,
            matched_skills: d.matched_skills, missing_skills: d.missing_skills, relevance: d.relevance,
          })
        }
      } catch { /* leave description empty — the drawer shows the no-description affordance */ }
      finally { setDescLoading(false) }
    }
  }

  // Open the tailoring workspace for a pasted JD WITHOUT auto-running the tailor —
  // the drawer shows the style picker so the user chooses faithful/balanced/aggressive
  // before tailoring (same as the search-job flow), instead of silently defaulting.
  function openPasteJd() {
    if (!cv) return toast.error('Upload your resume first.')
    if (jd.trim().length < 20) return toast.error('Paste a longer job description.')
    resetResult()
    setActiveJob({ jd })
  }

  async function runTailor(jdText: string) {
    if (!cv) return toast.error('Upload your resume first.')
    if (jdText.trim().length < 20) return toast.error('This posting has no description to tailor against.')
    setTailoring(true)
    try {
      const res = await api.tailor({ jd_text: jdText, resume_markdown: cv, style })
      setResult(res)
      setEditedResume(res.tailored_resume_markdown ?? '')
      setCoverLetter(null)
    } catch (e) { toast.error(err(e)) } finally { setTailoring(false) }
  }

  // Re-tailor the *edited* resume to the nearest full page so a small remainder
  // doesn't waste an under-used trailing page. Budget derived from the estimator.
  async function onFitToPage() {
    if (!activeJob || !editedResume.trim()) return
    const t = estimatePageTarget(editedResume)
    if (!t.underUsedTrailingPage) return
    setFitting(true)
    try {
      const res = await api.tailor({
        jd_text: activeJob.jd, resume_markdown: editedResume, style, target_pages: t.targetPages,
      })
      setResult(res)
      setEditedResume(res.tailored_resume_markdown ?? editedResume)
      setCoverLetter(null)
    } catch (e) { toast.error(err(e)) } finally { setFitting(false) }
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
      toast.success('Job description extracted — review it, then Tailor.')
    } catch (e) { toast.error(err(e)) } finally { setFetchingUrl(false) }
  }

  const m = result?.match
  const j = activeJob?.job
  // All predicted-fit values in the current results — the batch context that makes
  // each job's fit relative (Strong/Moderate/Weak + top-fit) rather than an absolute %.
  const allFits = jobs.map((job) => job.fit).filter((f): f is number => f != null)

  return (
    <div className="min-h-full">
      {(tailoring || generatingCl) && <div className="loadingbar" />}
      <header className="sticky top-0 z-20 border-b bg-background/85 backdrop-blur">
        <div className="mx-auto max-w-3xl px-5 h-14 flex items-center justify-between">
          <div className="flex items-baseline gap-2.5">
            <span className="display text-lg font-semibold">Overlap</span>
            <span className="eyebrow hidden sm:inline">ATS-safe · no sign-up</span>
          </div>
          <ThemeToggle />
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-5 pb-24">
        <section className="pt-12 pb-9">
          <p className="eyebrow mb-3">Deterministic · ATS-keyword matching</p>
          <h1 className="display text-[2rem] sm:text-[2.6rem] font-semibold leading-[1.06] max-w-2xl">
            See where your CV and the job <span className="text-primary">overlap</span> — then tailor to it.
          </h1>
          <p className="mt-4 max-w-xl leading-relaxed text-muted-foreground">
            An ATS-safe resume tuned to exactly what the posting asks for. The matcher only surfaces skills
            already in your CV — keyword-exact, never fabricated. No sign-up; it all stays in your browser.
          </p>
        </section>

        <div className="space-y-5">
          {/* Step 1 — resume */}
          <section className="rounded-xl border bg-card p-5 sm:p-6">
            <StepHead n="01" title="Your resume" hint={cv ? 'loaded' : undefined} />
            <div className="flex items-center gap-3 flex-wrap">
              <Button asChild variant={cv ? 'outline' : 'default'} disabled={uploading}>
                <label className="cursor-pointer">
                  {uploading ? 'Parsing…' : cv ? 'Replace PDF' : 'Upload resume PDF'}
                  <input type="file" accept="application/pdf" className="hidden"
                    onChange={(e) => e.target.files?.[0] && onUpload(e.target.files[0])} />
                </label>
              </Button>
              <span className="text-sm text-muted-foreground">
                {cv ? `${cv.length.toLocaleString()} chars · held in your browser only` : 'A text-based PDF, not a scan.'}
              </span>
              {cv && (
                <button onClick={() => setCvOpen((o) => !o)} className="eyebrow ml-auto hover:text-foreground">
                  {cvOpen ? '▾ hide markdown' : '▸ view / edit markdown'}
                </button>
              )}
            </div>
            {cv && cvOpen && (
              <div className="mt-4 space-y-1.5">
                <ResumeEditor value={cv} onChange={updateCv} showPageBadge />
                <p className="text-xs text-muted-foreground">
                  Fix any PDF-parsing glitches here — this is the exact CV used for matching and tailoring. Saved to your browser as you type.
                </p>
              </div>
            )}
          </section>

          {/* Step 2 — find a job */}
          <section className="rounded-xl border bg-card p-5 sm:p-6">
            <StepHead n="02" title="Find a job — or paste one" />
            <Tabs defaultValue="search">
              <TabsList>
                <TabsTrigger value="search">Search jobs</TabsTrigger>
                <TabsTrigger value="paste">Paste JD</TabsTrigger>
              </TabsList>

              <TabsContent value="search" className="space-y-4 pt-4">
                <div className="flex gap-2">
                  <Input value={query} onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && onSearch()}
                    placeholder={'e.g. "50 remote AI Engineer jobs on JobStreet, this week"'} />
                  <Button onClick={onSearch} disabled={searching}>{searching ? 'Searching…' : 'Search'}</Button>
                </div>
                <p className="eyebrow">
                  searches <span style={{ color: 'var(--loc)' }}>MyCareersFuture</span> ·{' '}
                  <span style={{ color: 'var(--loc)' }}>LinkedIn</span> ·{' '}
                  <span style={{ color: 'var(--loc)' }}>JobStreet</span> in parallel — or name one in your query
                </p>

                {interpreted && (
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="eyebrow mr-1">interpreted</span>
                    <span className="tok tok-have">{interpreted.keyword}</span>
                    <span className="tok">{interpreted.location}</span>
                    <span className="tok">{interpreted.platforms?.length ? interpreted.platforms.join(' · ') : 'all platforms'}</span>
                    {interpreted.date_posted && interpreted.date_posted !== 'any' && (
                      <span className="tok">{String(interpreted.date_posted).replace(/_/g, ' ')}</span>
                    )}
                    {interpreted.remote_options?.length ? <span className="tok">{interpreted.remote_options.join(' · ')}</span> : null}
                    {interpreted.experience_levels?.length ? <span className="tok">{interpreted.experience_levels.join(' · ')}</span> : null}
                    <span className="tok">max {interpreted.max_jobs}</span>
                  </div>
                )}

                {searching && (
                  <p className="font-mono text-xs text-muted-foreground animate-pulse">
                    ▸ scraping MyCareersFuture · LinkedIn · JobStreet — {jobs.length} found so far…
                  </p>
                )}
                {!searching && enriching > 0 && (
                  <p className="font-mono text-xs text-muted-foreground animate-pulse">
                    ▸ loading keywords for {enriching} more {enriching === 1 ? 'job' : 'jobs'}…
                  </p>
                )}

                <div className="space-y-2">
                  {jobs.map((job) => {
                    const have = job.matched_skills ?? []
                    const missing = job.missing_skills ?? []
                    const total = have.length + missing.length
                    return (
                      <button key={`${job.platform}-${job.external_id}`} onClick={() => openJob(job)}
                        className="w-full text-left rounded-lg border bg-card p-4 transition-colors hover:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="display font-semibold leading-tight truncate">{job.title}</p>
                            <div className="mt-1.5"><JobMeta job={job} /></div>
                          </div>
                          <div className="flex items-center gap-3 shrink-0">
                            <FitBadge fit={job.fit} allFits={allFits} />
                            {total > 0 && <Coverage have={have.length} total={total} />}
                            <span className="eyebrow">open →</span>
                          </div>
                        </div>
                        {total > 0 ? (
                          <div className="mt-3 flex flex-wrap items-center gap-2">
                            <Tokens have={have} missing={missing} />
                            {!job.has_description && enriching > 0 && <Spinner label="more…" />}
                          </div>
                        ) : enriching > 0 ? (
                          <Spinner label="extracting keywords…" className="mt-2" />
                        ) : (
                          <p className="mt-2 text-xs text-muted-foreground">No description found — open to view the posting.</p>
                        )}
                      </button>
                    )
                  })}
                </div>

                {jobs.length > 0 && !searching && (
                  <div className="space-y-4 pt-1">
                    <Button size="sm" variant="secondary" onClick={onAnalyze} disabled={analyzing}>
                      {analyzing ? 'Analyzing…' : `Insights on these ${jobs.length} jobs`}
                    </Button>
                    {insights && (
                      <div className="rounded-lg border bg-card p-5 space-y-5">
                        <div className="flex flex-wrap gap-x-6 gap-y-1.5 font-mono text-xs">
                          <span><span className="text-muted-foreground">jobs </span>{insights.job_count}</span>
                          {insights.coverage && (
                            <>
                              <span><span className="text-muted-foreground">avg match </span><b className={scoreColor(insights.coverage.avg_relevance)}>{insights.coverage.avg_relevance}%</b></span>
                              <span><span className="text-muted-foreground">strong ≥60% </span>{insights.coverage.strong_matches}</span>
                            </>
                          )}
                          {insights.salary?.max && <span><span className="text-muted-foreground">salary to </span>{insights.salary.max.toLocaleString()}</span>}
                        </div>
                        <div className="space-y-2">
                          <p className="eyebrow">most in-demand skills</p>
                          {insights.demanded_skills.slice(0, 10).map((d) => (
                            <div key={d.skill} className="flex items-center gap-3">
                              <span className="w-36 shrink-0 truncate font-mono text-xs">{d.skill}</span>
                              <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                                <div className="h-full rounded-full" style={{ width: `${d.pct}%`, background: d.candidate_has ? 'var(--have)' : 'var(--gap)' }} />
                              </div>
                              <span className="w-9 text-right font-mono text-xs tabular-nums text-muted-foreground">{d.pct}%</span>
                              <span className={`tok w-12 text-center shrink-0 ${d.candidate_has ? 'tok-have' : 'tok-gap'}`}>{d.candidate_has ? 'you' : 'gap'}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </TabsContent>

              <TabsContent value="paste" className="space-y-3 pt-4">
                <div className="flex gap-2">
                  <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="Paste a job posting URL to auto-extract…" />
                  <Button variant="outline" onClick={onFetchUrl} disabled={fetchingUrl}>{fetchingUrl ? 'Fetching…' : 'Fetch JD'}</Button>
                </div>
                <Textarea rows={8} value={jd} onChange={(e) => setJd(e.target.value)} placeholder="…or paste the full job description here" />
                <Button onClick={openPasteJd} disabled={tailoring}>Choose style &amp; tailor →</Button>
              </TabsContent>
            </Tabs>
          </section>
        </div>

        <footer className="mt-16 eyebrow">
          Overlap — stateless · deterministic matcher · your CV never leaves the browser
        </footer>
      </main>

      {/* Job-details drawer */}
      {activeJob && (
        <>
          <div className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm animate-in fade-in" onClick={() => setActiveJob(null)} />
          <aside className="fixed inset-y-0 right-0 z-50 w-full max-w-4xl bg-background border-l shadow-2xl overflow-y-auto animate-in slide-in-from-right duration-200">
            <div className="sticky top-0 z-10 flex h-14 items-center justify-between border-b bg-background/90 px-5 backdrop-blur">
              <span className="eyebrow">job details</span>
              <button onClick={() => setActiveJob(null)} className="text-muted-foreground hover:text-foreground text-lg leading-none" aria-label="Close">✕</button>
            </div>

            <div className="p-5 sm:p-6 space-y-6">
              {/* Header */}
              <div>
                <h2 className="display text-xl font-semibold leading-tight">{j?.title ?? 'Pasted job description'}</h2>
                {j && <div className="mt-2"><JobMeta job={j} size="lg" /></div>}
                <div className="mt-3 flex flex-wrap gap-2">
                  {j?.url && j.url !== '#' && (
                    <Button size="sm" variant="outline" asChild><a href={j.url} target="_blank" rel="noreferrer">View original ↗</a></Button>
                  )}
                </div>
              </div>

              {/* Skill overlap preview (search jobs) */}
              {descLoading ? (
                <p className="font-mono text-xs text-muted-foreground animate-pulse">▸ fetching the full job description…</p>
              ) : j && (j.matched_skills?.length || j.missing_skills?.length) ? (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <p className="eyebrow">skill overlap</p>
                    <div className="flex items-center gap-3">
                      <FitBadge fit={j.fit} allFits={allFits} />
                      <Coverage have={(j.matched_skills ?? []).length} total={(j.matched_skills ?? []).length + (j.missing_skills ?? []).length} />
                    </div>
                  </div>
                  <Tokens have={j.matched_skills ?? []} missing={j.missing_skills ?? []} />
                  <p className="text-xs text-muted-foreground">Green = already in your CV. Tailor to weave these in — the greyed ones are never fabricated.</p>
                </div>
              ) : null}

              {/* Intel panel */}
              <div className="space-y-4">
                {/* Red flags */}
                <div className="rounded-lg border p-4 space-y-2">
                  <p className="eyebrow">legitimacy check</p>
                  {redFlags === null ? (
                    <p className="font-mono text-xs text-muted-foreground animate-pulse">▸ scanning…</p>
                  ) : redFlagsFailed ? (
                    <p className="text-sm text-muted-foreground">Couldn't run the check — try again later.</p>
                  ) : redFlags.length === 0 ? (
                    <p className="text-sm" style={{ color: 'var(--have)' }}>No red flags detected.</p>
                  ) : (
                    <ul className="space-y-1.5">
                      {redFlags.map((f) => (
                        <li key={f.code} className="text-sm flex items-start gap-2">
                          <span className={`tok shrink-0 ${f.severity === 'high' ? 'tok-honesty' : f.severity === 'warn' ? 'tok-gap' : ''}`}>
                            {f.severity}
                          </span>
                          <span>
                            <b>{f.label}</b>{f.evidence ? ` — "${f.evidence}"` : ''}
                            <span className="text-muted-foreground text-xs"> · {f.source}</span>
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                  <p className="text-xs text-muted-foreground">Advisory heuristics — never blocks. Verify anything flagged yourself.</p>
                </div>
              </div>

              {/* Style + tailor */}
              <div className="rounded-lg border bg-muted/30 p-4 space-y-3">
                <div>
                  <p className="eyebrow mb-2">tailoring style</p>
                  <div className="grid grid-cols-3 gap-1 rounded-lg border bg-background p-1">
                    {STYLES.map((s) => (
                      <button key={s.key} onClick={() => setStyle(s.key)}
                        className={`rounded-md px-2 py-1.5 text-xs font-medium capitalize transition-colors ${
                          style === s.key ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'
                        }`}>{s.key}</button>
                    ))}
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">{STYLES.find((s) => s.key === style)!.hint}</p>
                </div>
                <Button onClick={() => runTailor(activeJob.jd)} disabled={tailoring || descLoading || !activeJob.jd.trim()}>
                  {tailoring ? 'Tailoring…' : descLoading ? 'Loading job…' : result ? 'Re-tailor' : 'Tailor my resume'}
                </Button>
                {tailoring && <p className="font-mono text-xs text-muted-foreground animate-pulse">▸ {stage}</p>}
                <p className="text-xs text-muted-foreground">Every style keeps you honest — no skill, title, or metric that isn’t in your CV.</p>
              </div>

              {/* Result */}
              {result && m && (
                <div className="space-y-5">
                  <div className="flex items-baseline gap-3">
                    <span className="eyebrow">match</span>
                    <span className={`font-mono text-2xl font-semibold tabular-nums ${scoreColor(m.overall_score)}`}>
                      {m.overall_score}<span className="text-sm text-muted-foreground">/100</span>
                    </span>
                    <span className="tok uppercase">{m.recommendation}</span>
                  </div>
                  <p className="text-sm text-muted-foreground">{m.reasoning}</p>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <div><p className="eyebrow mb-2">keywords you have ({m.keyword_have.length})</p><Tokens have={m.keyword_have} /></div>
                    <div><p className="eyebrow mb-2">wanted — not in your CV ({m.keyword_missing.length})</p><Tokens gap={m.keyword_missing} /></div>
                  </div>
                  <p className="text-xs text-muted-foreground">Only skills already in your CV are surfaced — the missing ones are never added to your resume.</p>

                  {/* Deterministic honesty check (guard against an absent field) */}
                  {(result.honesty ?? []).length === 0 ? (
                    <p className="flex items-center gap-2 text-xs" style={{ color: 'var(--have)' }}>
                      <span aria-hidden>✓</span> Honesty check passed — no invented roles, projects, metrics, or industries.
                    </p>
                  ) : (
                    <div className="rounded-lg border p-3 space-y-1.5"
                      style={{ borderColor: 'color-mix(in oklab, var(--honesty) 40%, transparent)', background: 'color-mix(in oklab, var(--honesty) 8%, transparent)' }}>
                      <p className="eyebrow" style={{ color: 'var(--honesty)' }}>honesty check — {(result.honesty ?? []).length} to verify</p>
                      {(result.honesty ?? []).map((h, i) => (
                        <p key={i} className="text-xs text-muted-foreground">
                          <span className="tok mr-1" style={{ color: 'var(--honesty)' }}>{h.kind}</span>{h.detail}
                        </p>
                      ))}
                      <p className="text-[11px] text-muted-foreground pt-0.5">Review these in the editable resume below — remove anything you can’t back up.</p>
                    </div>
                  )}

                  <div className="space-y-2">
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <p className="eyebrow">tailored resume — edit before download</p>
                      <div className="flex items-center gap-2">
                        {estimatePageTarget(editedResume).underUsedTrailingPage && (
                          <Button size="sm" variant="secondary" onClick={onFitToPage} disabled={fitting || tailoring}>
                            {fitting ? 'Fitting…' : `Fit to ${estimatePageTarget(editedResume).targetPages} page${estimatePageTarget(editedResume).targetPages > 1 ? 's' : ''}`}
                          </Button>
                        )}
                        <Button size="sm" onClick={async () => {
                          if (!editedResume.trim()) return
                          try { download(await api.resumePdf(editedResume), 'resume.pdf') } catch (e) { toast.error(err(e)) }
                        }} disabled={!editedResume.trim()}>Download resume PDF</Button>
                      </div>
                    </div>
                    <ResumeEditor value={editedResume} onChange={setEditedResume} showPageBadge />
                  </div>

                  <div className="rounded-lg border bg-muted/30 p-4 space-y-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Button size="sm" variant="secondary" onClick={onGenerateCl} disabled={generatingCl || !editedResume}>
                        {generatingCl ? 'Writing…' : coverLetter ? 'Regenerate cover letter' : 'Generate cover letter'}
                      </Button>
                      {coverLetter && (
                        <Button size="sm" variant="outline" onClick={async () => {
                          try { download(await api.coverLetterPdf(coverLetter), 'cover-letter.pdf') } catch (e) { toast.error(err(e)) }
                        }}>Download cover letter PDF</Button>
                      )}
                    </div>
                    {coverLetter && (
                      <Textarea rows={8} value={coverLetter} onChange={(e) => setCoverLetter(e.target.value)} className="text-sm" />
                    )}
                  </div>
                </div>
              )}

              {/* Full JD */}
              <details className="rounded-lg border bg-muted/20">
                <summary className="cursor-pointer px-4 py-2.5 eyebrow">full job description</summary>
                <p className="px-4 pb-4 pt-1 text-sm leading-relaxed whitespace-pre-wrap text-muted-foreground max-h-96 overflow-y-auto">
                  {descLoading ? 'Fetching…' : activeJob.jd || 'No description available — try “View original ↗”.'}
                </p>
              </details>
            </div>
          </aside>
        </>
      )}
    </div>
  )
}

// Stops any render error from blanking the whole page — shows a reload prompt
// instead. Your CV/results stay safe in localStorage across the reload.
class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }
  static getDerivedStateFromError(error: Error) { return { error } }
  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="mx-auto max-w-lg px-6 py-24 text-center">
        <p className="eyebrow mb-2">something broke</p>
        <h1 className="display text-xl font-semibold">The page hit an unexpected error</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Your resume and results are safe in your browser. If this started after an update, restart the backend
          (<code className="font-mono">python -m src.main serve</code>), then reload.
        </p>
        <Button className="mt-5" onClick={() => window.location.reload()}>Reload</Button>
        <pre className="mt-5 overflow-auto rounded-md border bg-muted/30 p-3 text-left text-xs text-muted-foreground">
          {String(this.state.error?.message || this.state.error)}
        </pre>
      </div>
    )
  }
}

export default function App() {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <ErrorBoundary>
        <Home />
      </ErrorBoundary>
      <Toaster richColors position="top-right" />
    </ThemeProvider>
  )
}
