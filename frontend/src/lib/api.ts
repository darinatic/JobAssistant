// Default to a RELATIVE base URL: in production FastAPI serves this SPA on the same
// origin, so `/tailor` etc. hit the same host. Local dev sets VITE_API_URL (see
// frontend/.env.development) to point at the separate backend on :8000.
const API_URL = import.meta.env.VITE_API_URL || ''

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body?.detail ?? detail
    } catch { /* non-json */ }
    throw new ApiError(res.status, `${res.status}: ${detail}`)
  }
  return res.json() as Promise<T>
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return handle<T>(res)
}

async function postForBlob(path: string, body: unknown): Promise<Blob> {
  const res = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json())?.detail ?? detail } catch { /* */ }
    throw new ApiError(res.status, `${res.status}: ${detail}`)
  }
  return res.blob()
}

// --- types ------------------------------------------------------------------
export interface Match {
  overall_score: number
  recommendation: string
  matched_required: string[]
  missing_required: string[]
  matched_preferred: string[]
  missing_preferred: string[]
  transferable_skills: string[]
  reasoning: string
  surfaceable_skills: string[]
  genuine_gaps: string[]
  keyword_have: string[]
  keyword_missing: string[]
}

export interface Job {
  platform: string
  external_id: string
  url: string
  title: string
  company: string
  location: string
  description: string
  relevance?: number
  fit?: number            // learned AI fit 0-100 (present only when the predictor is on)
  matched_skills?: string[]
  missing_skills?: string[]
  has_description?: boolean
  posted_date?: string
  salary_min?: number | null
  salary_max?: number | null
}

export interface Insights {
  job_count: number
  demanded_skills: { skill: string; count: number; pct: number; candidate_has: boolean }[]
  your_strengths: string[]
  your_gaps: string[]
  coverage: { avg_relevance: number; strong_matches: number } | null
  platforms: { platform: string; count: number }[]
  salary: { min: number | null; max: number | null; disclosed: number } | null
}

export interface RedFlag {
  code: string
  label: string
  severity: 'info' | 'warn' | 'high'
  evidence: string
  source: string
}

export interface TailorResult {
  tailored_resume_markdown: string | null
  cover_letter_text: string | null
  cover_letter_word_count: number | null
  match: Match
  changes_made: string[]
  keywords_added: string[]
  status: string
  errors: string[]
  honesty?: { kind: string; value: string; detail: string }[]
}

// --- endpoints --------------------------------------------------------------
export const api = {
  parseResume: async (file: File): Promise<{ markdown: string; chars: number }> => {
    const fd = new FormData()
    fd.append('file', file)
    return handle(await fetch(`${API_URL}/resume/parse`, { method: 'POST', body: fd }))
  },

  search: (body: { query: string; resume_markdown?: string }) =>
    postJson<{ jobs: Job[]; interpreted: Record<string, unknown> }>('/search', body),

  // Progressive search — NDJSON stream. Calls handlers as results arrive.
  searchStream: async (
    body: { query: string; resume_markdown?: string },
    h: { onInterpreted: (d: Record<string, any>) => void; onJob: (j: Job) => void; onDone: () => void },
    signal?: AbortSignal,
  ): Promise<void> => {
    const res = await fetch(`${API_URL}/search/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    })
    if (!res.ok || !res.body) throw new ApiError(res.status, `Search failed (${res.status})`)
    const reader = res.body.getReader()
    const dec = new TextDecoder()
    let buf = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() || ''
      for (const line of lines) {
        if (!line.trim()) continue
        const msg = JSON.parse(line)
        if (msg.type === 'interpreted') h.onInterpreted(msg.data)
        else if (msg.type === 'job') h.onJob(msg.data)
        else if (msg.type === 'done') h.onDone()
      }
    }
  },

  // Progressive keyword backfill for cards that came back description-less.
  enrichStream: async (
    body: { jobs: Job[]; resume_markdown?: string },
    h: { onUpdate: (u: Partial<Job> & { platform: string; external_id: string }) => void; onDone: () => void },
    signal?: AbortSignal,
  ): Promise<void> => {
    const res = await fetch(`${API_URL}/jobs/enrich/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    })
    if (!res.ok || !res.body) throw new ApiError(res.status, `Enrich failed (${res.status})`)
    const reader = res.body.getReader()
    const dec = new TextDecoder()
    let buf = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() || ''
      for (const line of lines) {
        if (!line.trim()) continue
        const msg = JSON.parse(line)
        if (msg.type === 'update') h.onUpdate(msg.data)
        else if (msg.type === 'done') h.onDone()
      }
    }
  },

  score: (body: { jd_text: string; resume_markdown: string }) => postJson<Match>('/score', body),

  insights: (body: { jobs: Job[]; resume_markdown?: string }) => postJson<Insights>('/insights', body),

  jobDescription: (body: { platform: string; external_id?: string; url?: string; title?: string; resume_markdown?: string }) =>
    postJson<{ description: string; has_description: boolean; matched_skills: string[]; missing_skills: string[]; relevance: number; fit?: number }>('/job/description', body),

  tailor: (body: {
    jd_text: string
    resume_markdown: string
    style?: 'faithful' | 'balanced' | 'aggressive'
    include_cover_letter?: boolean
    target_pages?: number
  }) => postJson<TailorResult>('/tailor', body),

  coverLetter: (body: { jd_text: string; resume_markdown: string }) =>
    postJson<{ cover_letter_text: string; word_count: number }>('/cover-letter', body),

  extractJd: (body: { url: string }) => postJson<{ jd_text: string }>('/extract-jd', body),

  redFlags: (body: {
    description?: string; company?: string
    salary_min?: number | null; salary_max?: number | null
    url?: string; posted_date?: string
  }) => postJson<{ flags: RedFlag[] }>('/job/red-flags', body),

  resumePdf: (resume_markdown: string) => postForBlob('/tailored/resume.pdf', { resume_markdown }),
  coverLetterPdf: (cover_letter_text: string) =>
    postForBlob('/tailored/cover-letter.pdf', { cover_letter_text }),
}
