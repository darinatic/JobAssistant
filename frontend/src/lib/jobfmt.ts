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

function amount(n: number): string {
  return `$${n.toLocaleString('en-US')}`
}
function periodSuffix(period?: string | null): string {
  return period === 'monthly' ? '/mo' : period === 'annual' ? '/yr' : ''
}

/** A disclosed salary as a compact string, or null when nothing is disclosed.
 *  Unknown period gets no suffix rather than guessing monthly. */
export function formatSalary(job: Job): string | null {
  const lo = job.salary_min
  const hi = job.salary_max
  const suf = periodSuffix(job.salary_period)
  if (lo != null && hi != null) return `${amount(lo)}–${amount(hi)}${suf}`
  if (hi != null) return `Up to ${amount(hi)}${suf}`
  if (lo != null) return `From ${amount(lo)}${suf}`
  return job.salary_raw ? job.salary_raw.trim() : null
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
