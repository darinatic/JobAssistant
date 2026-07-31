// Presentation + client-side refinement for job results. Pure helpers so they're
// unit-tested and the components stay declarative. Salary/experience come off the
// scrapers (see src/scrapers/parsing.py); many jobs disclose neither.

import type { Job } from './api'
import { fitTier, isTopFit } from './fit'

const LEVEL_LABELS: Record<string, string> = {
  entry_level: 'Entry',
  associate: 'Associate',
  mid_senior: 'Mid-Senior',
  director: 'Director',
  executive: 'Executive',
}

export const LEVEL_ORDER = ['entry_level', 'associate', 'mid_senior', 'director', 'executive'] as const

/** Normalized seniority as a clean display label, or null when unknown. The raw
 *  board string (e.g. "Professional") is kept on the job for a tooltip. */
export function experienceLabel(job: Job): string | null {
  return job.experience_level ? (LEVEL_LABELS[job.experience_level] ?? null) : null
}

/** Display label for a bare normalized level value (for filter chips). */
export function levelLabel(level: string): string {
  return LEVEL_LABELS[level] ?? level
}

function periodSuffix(period?: string | null): string {
  return period === 'monthly' ? '/mo' : period === 'annual' ? '/yr' : ''
}
// Compact "K" units so a long annual figure fits the salary column: 36000 -> 36K,
// 8500 -> 8.5K, 100000 -> 100K; < 1000 shown as-is.
function k(n: number): string {
  if (n < 1000) return String(n)
  const v = n / 1000
  return `${Number.isInteger(v) ? v : v.toFixed(1)}K`
}

/** Compact salary for a row (K units, keeps the board's posted period). Faithful to
 *  the posting — no monthly conversion; `salaryFull` gives the exact figure. */
export function formatSalary(job: Job): string | null {
  const lo = job.salary_min, hi = job.salary_max, suf = periodSuffix(job.salary_period)
  if (lo != null && hi != null) return `$${k(lo)}–${k(hi)}${suf}`
  if (hi != null) return `Up to $${k(hi)}${suf}`
  if (lo != null) return `From $${k(lo)}${suf}`
  return job.salary_raw ? job.salary_raw.trim() : null
}

/** Full un-abbreviated salary for a tooltip, e.g. "$36,000 – $100,000/yr". */
export function salaryFull(job: Job): string | null {
  const lo = job.salary_min, hi = job.salary_max, suf = periodSuffix(job.salary_period)
  const f = (n: number) => `$${n.toLocaleString('en-US')}`
  if (lo != null && hi != null) return `${f(lo)} – ${f(hi)}${suf}`
  if (hi != null) return `Up to ${f(hi)}${suf}`
  if (lo != null) return `From ${f(lo)}${suf}`
  return job.salary_raw ? job.salary_raw.trim() : null
}

// ---- posted date -----------------------------------------------------------

function relativeAge(ms: number): string {
  const days = Math.floor(ms / 86_400_000)
  if (days <= 0) return 'today'
  if (days < 7) return `${days}d ago`
  if (days < 30) return `${Math.floor(days / 7)}w ago`
  if (days < 365) return `${Math.floor(days / 30)}mo ago`
  return `${Math.floor(days / 365)}y ago`
}

function unitOf(word: string): string {
  const w = word.toLowerCase()
  if (w.startsWith('mo') || w.startsWith('month')) return 'mo'
  if (w[0] === 'h') return 'h'
  if (w[0] === 'w') return 'w'
  if (w[0] === 'y') return 'y'
  return 'd' // day(s) or unknown
}

/** Normalize a job's posted date to a compact "Xd ago". Handles ISO dates
 *  (MCF `createdAt`, LinkedIn `<time>`) and relative board text ("2d ago",
 *  "1 month ago"). `now` is injectable for deterministic tests. */
export function postedLabel(job: Job, now: number = Date.now()): string | null {
  const raw = (job.posted_date || '').trim()
  if (!raw) return null
  if (/\d{4}-\d{2}-\d{2}/.test(raw)) {
    const t = Date.parse(raw)
    if (!Number.isNaN(t)) return relativeAge(Math.max(0, now - t))
  }
  const m = raw.match(/(\d+)\s*([a-z]+)/i)
  if (m) return `${m[1]}${unitOf(m[2])} ago`
  return raw.length <= 16 ? raw.toLowerCase() : null
}

export function hasSalary(job: Job): boolean {
  return job.salary_min != null || job.salary_max != null || !!job.salary_raw
}

/** Upper salary bound normalized to a monthly figure, for threshold compares. */
export function monthlySalary(job: Job): number | null {
  const hi = job.salary_max ?? job.salary_min
  if (hi == null) return null
  return job.salary_period === 'annual' ? Math.round(hi / 12) : hi
}

export type Tier = 'top' | 'strong' | 'moderate' | 'weak' | 'unrated'

/** A job's fit tier within the current batch — the same classification the row
 *  badge shows, so the tier filter and the badge always agree. */
export function jobTier(job: Job, allFits: number[]): Tier {
  if (job.fit == null) return 'unrated'
  if (isTopFit(job.fit, allFits)) return 'top'
  return fitTier(job.fit, allFits)
}

// ---- client-side refinement over the already-fetched results ---------------

export type RefineState = {
  levels: string[] // experience_level values
  platforms: string[]
  tiers: Tier[]
  minSalary: number // monthly; 0 = any
  hasSalaryOnly: boolean
}

export const EMPTY_REFINE: RefineState = {
  levels: [], platforms: [], tiers: [], minSalary: 0, hasSalaryOnly: false,
}

export function refineActive(r: RefineState): boolean {
  return r.levels.length > 0 || r.platforms.length > 0 || r.tiers.length > 0
    || r.minSalary > 0 || r.hasSalaryOnly
}

export function applyRefine(jobs: Job[], r: RefineState, allFits: number[]): Job[] {
  if (!refineActive(r)) return jobs
  return jobs.filter((job) => {
    if (r.levels.length && !(job.experience_level && r.levels.includes(job.experience_level))) return false
    if (r.platforms.length && !r.platforms.includes(job.platform)) return false
    if (r.tiers.length && !r.tiers.includes(jobTier(job, allFits))) return false
    if (r.hasSalaryOnly && !hasSalary(job)) return false
    if (r.minSalary > 0) {
      const m = monthlySalary(job)
      if (m == null || m < r.minSalary) return false
    }
    return true
  })
}
