import { Component, type ReactNode, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { Toaster } from '@/components/ui/sonner'
import { api, ApiError, type Insights, type Job, type RedFlag, type TailorResult } from '@/lib/api'
import { ResumeWorkspace } from '@/components/ResumeWorkspace'
import { estimatePageTarget } from '@/lib/page-fit'
import { fitLabel } from '@/lib/fit'
import { patchSkillsLine, skillInResume } from '@/lib/skills'
import {
  formatSalary, experienceLabel, hasSalary, jobTier, applyRefine, refineActive,
  levelLabel, EMPTY_REFINE, LEVEL_ORDER, type RefineState, type Tier,
} from '@/lib/jobfmt'
import { SegmentedBar } from '@/overlap/SegmentedBar'
import {
  DATE_OPTIONS, EXPERIENCE_OPTIONS, PLATFORM_OPTIONS, REMOTE_OPTIONS, MAX_JOBS_OPTIONS,
  DEFAULT_FILTERS, toRequestFilters, type FilterState,
} from '@/lib/search-filters'

// Stable per-job key for the pending/enrichment set.
const jobKey = (j: { platform: string; external_id: string }) => `${j.platform}:${j.external_id}`

// Ranking: a job with a description sorts by learned fit (else lexical relevance);
// jobs still lacking a description (e.g. LinkedIn-walled) sink below all rated ones
// rather than floating up on a misleading title-only relevance.
const jobRank = (j: Job) => (j.has_description ? (j.fit ?? j.relevance ?? 0) : -1)

const CV_KEY = 'overlap.cv'
const SEARCH_KEY = 'overlap.search'

type ActiveJob = { job?: Job; jd: string }
type View = 'upload' | 'search' | 'job'

const STYLES = [
  { key: 'faithful' as const, hint: 'Keep everything. Reorder and rephrase only, safest, nothing is cut.' },
  { key: 'aggressive' as const, hint: 'Restructure, cut low-relevance sections, hard one page. Maximum fit.' },
]
type SavedSearch = { query?: string; interpreted?: Record<string, any> | null; jobs?: Job[]; filters?: FilterState }

function loadSearch(): SavedSearch {
  try { return JSON.parse(localStorage.getItem(SEARCH_KEY) || '{}') } catch { return {} }
}

function scoreColor(s: number): string {
  if (s >= 80) return 'var(--have)'
  if (s >= 60) return 'var(--ink)'
  if (s >= 40) return 'var(--gap)'
  return 'var(--honesty)'
}

function err(e: unknown): string {
  if (e instanceof ApiError) return e.message
  const msg = e instanceof Error ? e.message : String(e)
  if (/failed to fetch|networkerror|load failed|err_connection/i.test(msg))
    return "Can't reach the server, make sure the backend is running, then try again."
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

// ---- industrial primitives -------------------------------------------------

function Chip({ label, tone = 'gap' }: { label: string; tone?: 'have' | 'gap' | 'honesty' }) {
  if (tone === 'have') return <span className="ov-chip ov-chip-have">{label}</span>
  if (tone === 'honesty') return <span className="ov-chip" style={{ border: '1px solid var(--honesty)', color: 'var(--honesty)' }}>{label}</span>
  return <span className="ov-chip ov-chip-gap">{label}</span>
}

function Tokens({ have = [], gap = [], missing = [], honesty = [] }: { have?: string[]; gap?: string[]; missing?: string[]; honesty?: string[] }) {
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
function SkillChip({ skill, tone, added, onToggle }: {
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

function Coverage({ have, total }: { have: number; total: number }) {
  const pct = total ? have / total : 0
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }} title={`${have} of ${total} skills matched`}>
      <span className="ov-num" style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 700, color: 'var(--ink)' }}>{have}/{total}</span>
      <div style={{ width: 60 }}><SegmentedBar segments={9} pct={pct} height={8} live={false} /></div>
    </div>
  )
}

// Relative fit within the current results, never the raw score.
function FitBadge({ fit, allFits }: { fit?: number; allFits: number[] }) {
  if (fit == null) return null
  const { label } = fitLabel(fit, allFits)
  const l = label.toLowerCase()
  const stampClass = l.includes('top') ? 'ov-stamp-topfit' : l.includes('strong') ? 'ov-stamp-strong' : 'ov-stamp-moderate'
  return <span className={`ov-stamp ${stampClass}`} title="AI-predicted fit, relative to these results">{label}</span>
}

function JobMeta({ job }: { job: Job }) {
  return (
    <span className="ov-mono" style={{ fontSize: 11, fontFamily: 'var(--font-mono)', letterSpacing: '0.03em', color: 'var(--dim)' }}>
      <span style={{ color: 'var(--ink)' }}>{job.company}</span>
      {'  ·  '}<span style={{ color: 'var(--geo)' }}>◍ {job.location || 'Singapore'}</span>
      {'  ·  '}{job.platform}
    </span>
  )
}

// Salary (ink mono, tabular) over a small seniority stamp — the right-aligned
// readout column of a job row / the tailor header. Null when neither is disclosed.
function SalaryLevel({ job, align = 'right' }: { job: Job; align?: 'right' | 'left' }) {
  const salary = formatSalary(job)
  const level = experienceLabel(job)
  if (!salary && !level) return null
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5, alignItems: align === 'right' ? 'flex-end' : 'flex-start' }}>
      {salary && (
        <span className="ov-num" style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 700, color: 'var(--ink)', whiteSpace: 'nowrap' }}>{salary}</span>
      )}
      {level && (
        <span className="ov-stamp ov-stamp-info" title={job.experience_raw ?? undefined} style={{ fontSize: 9 }}>{level}</span>
      )}
    </div>
  )
}

function Home() {
  const [cv, setCv] = useState<string>(() => localStorage.getItem(CV_KEY) || '')
  const [uploading, setUploading] = useState(false)
  const [view, setView] = useState<View>(() => (localStorage.getItem(CV_KEY) ? 'search' : 'upload'))

  function updateCv(md: string) {
    setCv(md)
    try { localStorage.setItem(CV_KEY, md) } catch { /* quota */ }
  }

  const saved = useRef<SavedSearch>(loadSearch()).current
  const [query, setQuery] = useState(saved.query ?? 'AI Engineer jobs in Singapore')
  const [interpreted, setInterpreted] = useState<Record<string, any> | null>(saved.interpreted ?? null)
  const [jobs, setJobs] = useState<Job[]>(saved.jobs ?? [])
  const [filters, setFilters] = useState<FilterState>(saved.filters ?? DEFAULT_FILTERS)
  const [searching, setSearching] = useState(false)
  const [pending, setPending] = useState<Set<string>>(() => new Set())
  const [refine, setRefine] = useState<RefineState>(EMPTY_REFINE)  // client-side result refinement
  const [insights, setInsights] = useState<Insights | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [downloading, setDownloading] = useState<'resume' | 'cover' | null>(null)
  const [progress, setProgress] = useState<{ found: number; target: number; scanned: number; unfetchable?: number } | null>(null)
  const [floor, setFloor] = useState(false)
  const searchAbort = useRef<AbortController | null>(null)
  const enrichAbort = useRef<AbortController | null>(null)

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

  useEffect(() => {
    if (!tailoring) { setStage(''); return }
    const stages = ['reading the posting', 'matching against your cv', 'drafting · streaming', 'honesty lint · checking every claim']
    let i = 0
    setStage(stages[0])
    const id = setInterval(() => { i = Math.min(i + 1, stages.length - 1); setStage(stages[i]) }, 3500)
    return () => clearInterval(id)
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
      return cv ? [...next].sort((a, b) => jobRank(b) - jobRank(a)) : next
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
        { jobs: need, resume_markdown: cv || undefined },
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

  function resetResult() { setResult(null); setEditedResume(''); setCoverLetter(null) }

  function clearResults() {
    setJobs([]); setInsights(null); setPending(new Set()); setInterpreted(null)
    setProgress(null); setFloor(false); setRefine(EMPTY_REFINE)
    try { localStorage.removeItem(SEARCH_KEY) } catch { /* ignore */ }
  }

  async function onUpload(file: File) {
    setUploading(true)
    try {
      const { markdown, chars } = await api.parseResume(file)
      updateCv(markdown)
      toast.success(`Resume loaded (${chars.toLocaleString()} chars), review the markdown for parsing glitches`)
    } catch (e) { toast.error(err(e)) } finally { setUploading(false) }
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
    if (!cv) return toast.error('Upload your resume first, then search.')
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
          resume_markdown: cv || undefined,
          filters: toRequestFilters(filters, query, interpreted?.location ?? 'Singapore'),
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
              return cv ? next.sort((a, b) => jobRank(b) - jobRank(a)) : next
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
    try { setInsights(await api.insights({ jobs: js, resume_markdown: cv || undefined })) }
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
          title: job.title, resume_markdown: cv || undefined,
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
    if (!cv) return toast.error('Upload your resume first.')
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
    if (!cv) return toast.error('Upload your resume first.')
    if (jdText.trim().length < 20) return toast.error('This posting has no description to tailor against.')
    setTailoring(true)
    try {
      const res = await api.tailor({ jd_text: jdText, resume_markdown: cv, style })
      setResult(res)
      setEditedResume(applySkillAdditions(res.tailored_resume_markdown ?? '', res.match))
      setCoverLetter(null)
    } catch (e) { toast.error(err(e)) } finally { setTailoring(false) }
  }

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
      setEditedResume(applySkillAdditions(res.tailored_resume_markdown ?? editedResume, res.match))
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
      toast.success('Job description extracted, review it, then Tailor.')
    } catch (e) { toast.error(err(e)) } finally { setFetchingUrl(false) }
  }

  const m = result?.match
  const j = activeJob?.job
  const allFits = jobs.map((job) => job.fit).filter((f): f is number => f != null)

  const goStage = (v: View) => {
    if (v === 'search' && !cv) return toast.error('Upload your resume first.')
    if (v === 'job' && !activeJob) return
    setView(v)
  }

  return (
    <div className="ov" style={{ minHeight: '100%' }}>
      <div className="ov-shell" style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
        <StageBar view={view} cv={!!cv} hasJob={!!activeJob} onGo={goStage} />

        {view === 'upload' && (
          <StageResume cv={cv} uploading={uploading} onUpload={onUpload} updateCv={updateCv} onContinue={() => goStage('search')} />
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
          <span className="ov-micro" style={{ fontSize: 9 }}>overlap · a portfolio project · your cv stays in this browser</span>
        </footer>
      </div>
    </div>
  )
}

// ---- stage bar -------------------------------------------------------------

function StageBar({ view, cv, hasJob, onGo }: { view: View; cv: boolean; hasJob: boolean; onGo: (v: View) => void }) {
  const items: [View, string, boolean][] = [
    ['upload', '01 resume', true],
    ['search', '02 search', cv],
    ['job', '03 tailor', hasJob],
  ]
  return (
    <header style={{ position: 'sticky', top: 0, zIndex: 20, display: 'flex', alignItems: 'stretch', background: 'var(--surface)', borderBottom: '2px solid var(--ink)' }}>
      <a href="/" style={{ background: 'var(--ink)', color: 'var(--paper)', fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 14, padding: '0 16px', textDecoration: 'none', display: 'flex', alignItems: 'center' }}>OVERLAP</a>
      <nav role="tablist" style={{ display: 'flex' }}>
        {items.map(([v, label, enabled]) => (
          <button key={v} role="tab" aria-selected={view === v} disabled={!enabled} onClick={() => onGo(v)}
            className="ov-mono"
            style={{
              fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 11, letterSpacing: '0.14em', textTransform: 'uppercase',
              padding: '0 20px', minHeight: 46, borderRight: '1px solid var(--rule)', cursor: enabled ? 'pointer' : 'not-allowed',
              background: view === v ? 'var(--ink)' : 'transparent', color: view === v ? 'var(--paper)' : enabled ? 'var(--dim)' : 'var(--hair)',
            }}>
            {label}
          </button>
        ))}
      </nav>
      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8, padding: '0 16px' }}>
        <span style={{ width: 9, height: 9, background: cv ? 'var(--have)' : 'var(--gap)', display: 'inline-block' }} />
        <span className="ov-micro ov-hide-sm" style={{ fontSize: 9 }}>{cv ? `cv loaded · local` : 'no cv · local'}</span>
      </div>
    </header>
  )
}

// ---- stage 01 resume -------------------------------------------------------

function StageResume({ cv, uploading, onUpload, updateCv, onContinue }: {
  cv: string; uploading: boolean; onUpload: (f: File) => void; updateCv: (md: string) => void; onContinue: () => void
}) {
  const onFile = (e: React.ChangeEvent<HTMLInputElement>) => e.target.files?.[0] && onUpload(e.target.files[0])
  if (!cv) {
    return (
      <div className="ov-pad" style={{ flex: 1 }}>
        <div className="ov-eyebrow" style={{ marginBottom: 16 }}>step 01 / 03</div>
        <h1 className="ov-h1" style={{ maxWidth: 640 }}>Three boards, read at once.</h1>
        <p className="ov-lead" style={{ marginTop: 20 }}>
          Scored against your own words. Nothing stored, your CV stays in this browser.
        </p>
        <label style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 11, border: '2px dashed var(--ink)', padding: '34px 18px', marginTop: 28, cursor: 'pointer', maxWidth: 520 }}>
          <span className="ov-mono" style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 26, color: 'var(--ink)' }}>[ + ]</span>
          <span className="ov-micro" style={{ fontWeight: 700, fontSize: 11, letterSpacing: '0.14em' }}>{uploading ? 'parsing…' : 'upload resume pdf'}</span>
          <input type="file" accept="application/pdf" style={{ display: 'none' }} onChange={onFile} />
        </label>
        <div style={{ display: 'flex', border: '2px solid var(--ink)', marginTop: 32, maxWidth: 520 }}>
          {[['3', 'boards'], ['~1ms', 'match'], ['0', 'stored']].map(([n, l], i) => (
            <div key={l} style={{ flex: 1, padding: '14px 16px', borderRight: i < 2 ? '1px solid var(--rule)' : undefined }}>
              <div className="ov-num" style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 22, color: 'var(--ink)' }}>{n}</div>
              <div className="ov-micro" style={{ fontSize: 9, marginTop: 4 }}>{l}</div>
            </div>
          ))}
        </div>
      </div>
    )
  }
  return (
    <div className="ov-pad" style={{ flex: 1 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
        <div className="ov-eyebrow">step 01 / 03 · markdown source</div>
        <div style={{ display: 'flex', gap: 10 }}>
          <label className="ov-btn" style={{ cursor: 'pointer' }}>
            {uploading ? 'parsing…' : 'replace pdf'}
            <input type="file" accept="application/pdf" style={{ display: 'none' }} onChange={onFile} />
          </label>
          <button className="ov-btn ov-btn-ink" onClick={onContinue}>continue to search →</button>
        </div>
      </div>
      <ResumeWorkspace value={cv} onChange={updateCv} showPageBadge label="your resume" />
      <p className="ov-micro" style={{ fontSize: 9, marginTop: 12, letterSpacing: '0.08em' }}>
        fix any pdf-parsing glitches here. this exact cv is used for matching and tailoring. saved to your browser as you type.
      </p>
    </div>
  )
}

// ---- filter rows -----------------------------------------------------------

function FilterRow({ label, note, children }: { label: string; note?: string; children: ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'stretch', borderBottom: '1px solid var(--rule)', flexWrap: 'wrap' }}>
      <span className="ov-micro" style={{ width: 110, flexShrink: 0, padding: '8px 12px', borderRight: '1px solid var(--rule)', fontSize: 9, alignSelf: 'center' }}>{label}</span>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', flex: 1 }}>{children}</div>
      {note && <span className="ov-micro" style={{ marginLeft: 'auto', alignSelf: 'center', padding: '0 12px', fontSize: 9, color: 'var(--dim)' }}>{note}</span>}
    </div>
  )
}

function FilterBtn({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button onClick={onClick} className="ov-mono"
      style={{ fontFamily: 'var(--font-mono)', fontSize: 11, padding: '8px 12px', borderRight: '1px solid var(--rule)', cursor: 'pointer', whiteSpace: 'nowrap', background: active ? 'var(--ink)' : 'transparent', color: active ? 'var(--paper)' : 'var(--dim)', fontWeight: active ? 700 : 400 }}>
      {children}
    </button>
  )
}

function FilterRows({ filters, setDate, setMax, toggleFilter }: {
  filters: FilterState; setDate: (v: string) => void; setMax: (n: number) => void
  toggleFilter: (k: 'experienceLevels' | 'remoteOptions' | 'platforms', v: string) => void
}) {
  return (
    <div style={{ borderBottom: '2px solid var(--ink)' }}>
      <FilterRow label="date">
        {DATE_OPTIONS.map((o) => <FilterBtn key={o.value} active={filters.datePosted === o.value} onClick={() => setDate(o.value)}>{o.label}</FilterBtn>)}
      </FilterRow>
      <FilterRow label="max jobs">
        {MAX_JOBS_OPTIONS.map((n) => <FilterBtn key={n} active={filters.maxJobs === n} onClick={() => setMax(n)}>{n}</FilterBtn>)}
      </FilterRow>
      <FilterRow label="boards" note="none = all three">
        {PLATFORM_OPTIONS.map((o) => <FilterBtn key={o.value} active={filters.platforms.includes(o.value)} onClick={() => toggleFilter('platforms', o.value)}>{o.label}</FilterBtn>)}
      </FilterRow>
      <FilterRow label="experience" note="li + mcf only">
        {EXPERIENCE_OPTIONS.map((o) => <FilterBtn key={o.value} active={filters.experienceLevels.includes(o.value)} onClick={() => toggleFilter('experienceLevels', o.value)}>{o.label}</FilterBtn>)}
      </FilterRow>
      <FilterRow label="remote" note="li only">
        {REMOTE_OPTIONS.map((o) => <FilterBtn key={o.value} active={filters.remoteOptions.includes(o.value)} onClick={() => toggleFilter('remoteOptions', o.value)}>{o.label}</FilterBtn>)}
      </FilterRow>
    </div>
  )
}

// ---- refine bar (client-side, over the already-fetched results) ------------

const MIN_SALARY_OPTS = [0, 3000, 5000, 8000, 10000]
const TIER_OPTS: [Tier, string][] = [
  ['top', 'top fit'], ['strong', 'strong'], ['moderate', 'moderate'], ['weak', 'weak'], ['unrated', 'unrated'],
]

function RefineBar({ jobs, allFits, refine, setRefine, visibleCount }: {
  jobs: Job[]; allFits: number[]; refine: RefineState; setRefine: (u: RefineState) => void; visibleCount: number
}) {
  const levelsPresent = LEVEL_ORDER.filter((l) => jobs.some((j) => j.experience_level === l))
  const platformsPresent = [...new Set(jobs.map((j) => j.platform))]
  const tiersPresent = TIER_OPTS.filter(([t]) => jobs.some((j) => jobTier(j, allFits) === t))
  const anySalary = jobs.some(hasSalary)
  const active = refineActive(refine)

  const toggle = (key: 'levels' | 'platforms', v: string) =>
    setRefine({ ...refine, [key]: refine[key].includes(v) ? refine[key].filter((x) => x !== v) : [...refine[key], v] })
  const toggleTier = (t: Tier) =>
    setRefine({ ...refine, tiers: refine.tiers.includes(t) ? refine.tiers.filter((x) => x !== t) : [...refine.tiers, t] })

  return (
    <div style={{ borderBottom: '2px solid var(--ink)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 20px', background: 'var(--panel)', borderBottom: '1px solid var(--rule)' }}>
        <span className="ov-micro" style={{ fontSize: 9 }}>refine these results · {visibleCount} of {jobs.length} shown</span>
        {active && <button onClick={() => setRefine(EMPTY_REFINE)} className="ov-micro" style={{ fontSize: 9, background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--dim)' }}>reset ✕</button>}
      </div>
      {levelsPresent.length > 0 && (
        <FilterRow label="experience">
          {levelsPresent.map((l) => <FilterBtn key={l} active={refine.levels.includes(l)} onClick={() => toggle('levels', l)}>{levelLabel(l)}</FilterBtn>)}
        </FilterRow>
      )}
      {platformsPresent.length > 1 && (
        <FilterRow label="board">
          {platformsPresent.map((p) => <FilterBtn key={p} active={refine.platforms.includes(p)} onClick={() => toggle('platforms', p)}>{p}</FilterBtn>)}
        </FilterRow>
      )}
      {tiersPresent.length > 1 && (
        <FilterRow label="fit">
          {tiersPresent.map(([t, label]) => <FilterBtn key={t} active={refine.tiers.includes(t)} onClick={() => toggleTier(t)}>{label}</FilterBtn>)}
        </FilterRow>
      )}
      {anySalary && (
        <FilterRow label="salary">
          <FilterBtn active={refine.hasSalaryOnly} onClick={() => setRefine({ ...refine, hasSalaryOnly: !refine.hasSalaryOnly })}>disclosed</FilterBtn>
          {MIN_SALARY_OPTS.map((n) => (
            <FilterBtn key={n} active={refine.minSalary === n} onClick={() => setRefine({ ...refine, minSalary: n })}>
              {n === 0 ? 'any' : `${n / 1000}k+/mo`}
            </FilterBtn>
          ))}
        </FilterRow>
      )}
    </div>
  )
}

// ---- results table ---------------------------------------------------------

function ResultsTable({ jobs, pending, allFits, onOpen, refine, setRefine }: {
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

// ---- paste jd --------------------------------------------------------------

function PasteJd({ url, setUrl, jd, setJd, fetchingUrl, onFetchUrl, onTailor, tailoring }: {
  url: string; setUrl: (v: string) => void; jd: string; setJd: (v: string) => void
  fetchingUrl: boolean; onFetchUrl: () => void; onTailor: () => void; tailoring: boolean
}) {
  return (
    <div className="ov-pad">
      <div style={{ display: 'flex', border: '2px solid var(--ink)' }}>
        <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="Paste a job posting URL to auto-extract…"
          style={{ flex: 1, minWidth: 0, border: 'none', outline: 'none', background: 'transparent', fontFamily: 'var(--font-mono)', fontSize: 13, padding: '12px 14px', color: 'var(--ink)' }} />
        <button onClick={onFetchUrl} disabled={fetchingUrl} className="ov-btn" style={{ border: 'none', borderLeft: '2px solid var(--ink)' }}>{fetchingUrl ? 'fetching…' : 'fetch jd'}</button>
      </div>
      <div className="ov-micro" style={{ fontSize: 9, margin: '12px 0 8px' }}>…or paste the description</div>
      <textarea value={jd} onChange={(e) => setJd(e.target.value)} placeholder="Paste the full job description here"
        style={{ width: '100%', minHeight: 300, border: '2px solid var(--ink)', outline: 'none', background: 'var(--surface)', fontFamily: 'var(--font-mono)', fontSize: 13, lineHeight: 1.7, padding: 16, color: 'var(--ink)', resize: 'vertical' }} />
      <button className="ov-btn ov-btn-ink" style={{ marginTop: 14 }} onClick={onTailor} disabled={tailoring}>choose style &amp; tailor →</button>
    </div>
  )
}

// ---- readout rail ----------------------------------------------------------

function ReadoutRail({ insights, analyzing, scoreColor, className }: { insights: Insights | null; analyzing: boolean; scoreColor: (n: number) => string; className?: string }) {
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
            {insights.demanded_skills.slice(0, 8).map((d) => (
              <div key={d.skill} style={{ display: 'grid', gridTemplateColumns: '1fr 34px', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <div>
                  <div className="ov-mono" style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--dim)', marginBottom: 3 }}>{d.skill}</div>
                  <div style={{ display: 'flex', height: 7, background: 'var(--hair)' }}>
                    <div style={{ width: `${d.pct}%`, background: d.candidate_has ? 'var(--have)' : 'var(--gap)' }} />
                  </div>
                </div>
                <span className="ov-mono ov-num" style={{ fontFamily: 'var(--font-mono)', fontSize: 11, textAlign: 'right', color: 'var(--dim)' }}>{d.pct}%</span>
              </div>
            ))}
            <div className="ov-micro" style={{ fontSize: 8, marginTop: 8, lineHeight: 1.6 }}>filled green = in your cv / amber = gap to close</div>
          </div>
        </div>
      ) : analyzing ? (
        <div className="ov-micro" style={{ padding: '16px', fontSize: 9 }}>▸ analyzing insights…</div>
      ) : (
        <div className="ov-micro" style={{ padding: '16px', fontSize: 9, lineHeight: 1.7 }}>cv + results held in localstorage only. nothing server-side.</div>
      )}
    </aside>
  )
}

// ---- stage 03 tailor -------------------------------------------------------

function Pipeline({ tailoring, result, downloading }: { tailoring: boolean; result: TailorResult | null; downloading: string | null }) {
  const done = !!result
  const rows: [string, string, string][] = [
    ['parse jd', 'haiku 4.5', tailoring || done ? 'var(--have)' : 'var(--hair)'],
    ['match skills', 'local · 1ms', tailoring || done ? 'var(--have)' : 'var(--hair)'],
    ['tailor', 'sonnet 4.5', done ? 'var(--have)' : tailoring ? 'var(--ink)' : 'var(--hair)'],
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

type TailorProps = {
  activeJob: ActiveJob; j?: Job; m?: TailorResult['match']; result: TailorResult | null; allFits: number[]
  descLoading: boolean; redFlags: RedFlag[] | null; redFlagsFailed: boolean
  style: 'faithful' | 'aggressive'; setStyle: (s: 'faithful' | 'aggressive') => void; tailoring: boolean; stage: string
  editedResume: string; setEditedResume: (v: string) => void
  coverLetter: string | null; setCoverLetter: (v: string) => void; generatingCl: boolean
  fitting: boolean; downloading: 'resume' | 'cover' | null; setDownloading: (v: 'resume' | 'cover' | null) => void
  onBack: () => void; onTailor: () => void; onFitToPage: () => void; onGenerateCl: () => void
}

function StageTailor(p: TailorProps) {
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
                {(result.honesty ?? []).length === 0 && <span className="ov-stamp ov-stamp-have">honesty ✓</span>}
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

          {/* full jd */}
          <details style={{ border: '1px solid var(--rule)' }}>
            <summary className="ov-micro" style={{ cursor: 'pointer', padding: '10px 14px', fontSize: 9 }}>full job description</summary>
            <p style={{ padding: '4px 14px 14px', fontSize: 13, lineHeight: 1.6, whiteSpace: 'pre-wrap', color: 'var(--body)', maxHeight: 384, overflowY: 'auto' }}>
              {descLoading ? 'Fetching…' : activeJob.jd || 'No description available, try "original ↗".'}
            </p>
          </details>
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

// Stops any render error from blanking the whole page.
class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }
  static getDerivedStateFromError(error: Error) { return { error } }
  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="ov" style={{ minHeight: '100vh' }}>
        <div style={{ maxWidth: 520, margin: '0 auto', padding: '96px 24px', textAlign: 'center' }}>
          <div className="ov-eyebrow" style={{ marginBottom: 8 }}>something broke</div>
          <h1 className="ov-h2">The page hit an unexpected error</h1>
          <p style={{ marginTop: 12, fontSize: 14, color: 'var(--body)' }}>
            Your resume and results are safe in your browser. If this started after an update, restart the backend
            (<code style={{ fontFamily: 'var(--font-mono)' }}>python -m src.main serve</code>), then reload.
          </p>
          <button className="ov-btn ov-btn-ink" style={{ marginTop: 20 }} onClick={() => window.location.reload()}>reload</button>
          <pre style={{ marginTop: 20, overflow: 'auto', border: '1px solid var(--rule)', background: 'var(--panel)', padding: 12, textAlign: 'left', fontSize: 11, color: 'var(--dim)' }}>
            {String(this.state.error?.message || this.state.error)}
          </pre>
        </div>
      </div>
    )
  }
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
