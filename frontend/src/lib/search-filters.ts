// Deterministic filter controls for hybrid search. Enum VALUES must match the
// backend NL vocab in src/search_nlp.py exactly; labels are display-only.
import type { SearchFilters } from './api'

export const DATE_OPTIONS = [
  { value: 'any', label: 'Any time' },
  { value: 'past_24_hours', label: 'Past 24 hours' },
  { value: 'past_week', label: 'Past week' },
  { value: 'past_month', label: 'Past month' },
]
export const EXPERIENCE_OPTIONS = [
  { value: 'entry_level', label: 'Entry' },
  { value: 'associate', label: 'Associate' },
  { value: 'mid_senior', label: 'Mid-Senior' },
  { value: 'director', label: 'Director' },
  { value: 'executive', label: 'Executive' },
]
export const PLATFORM_OPTIONS = [
  { value: 'mycareersfuture', label: 'MyCareersFuture' },
  { value: 'linkedin', label: 'LinkedIn' },
  { value: 'jobstreet', label: 'JobStreet' },
]
export const REMOTE_OPTIONS = [
  { value: 'on_site', label: 'On-site' },
  { value: 'remote', label: 'Remote' },
  { value: 'hybrid', label: 'Hybrid' },
]
export const MAX_JOBS_OPTIONS = [25, 50, 100, 200, 300]

export type FilterState = {
  datePosted: string
  experienceLevels: string[]
  remoteOptions: string[]
  platforms: string[]
  maxJobs: number
}

export const DEFAULT_FILTERS: FilterState = {
  datePosted: 'any',
  experienceLevels: [],
  remoteOptions: [],
  platforms: [],
  maxJobs: 25,
}

// interpreted SearchQuery (from the stream) -> control state, so the AI parse
// visibly fills the dropdowns.
export function filtersFromInterpreted(d: Record<string, any>): FilterState {
  return {
    datePosted: d?.date_posted ?? DEFAULT_FILTERS.datePosted,
    experienceLevels: Array.isArray(d?.experience_levels) ? d.experience_levels : [],
    remoteOptions: Array.isArray(d?.remote_options) ? d.remote_options : [],
    platforms: Array.isArray(d?.platforms) ? d.platforms : [],
    maxJobs: typeof d?.max_jobs === 'number' ? d.max_jobs : DEFAULT_FILTERS.maxJobs,
  }
}

// control state -> backend `filters` payload (deterministic search path).
export function toRequestFilters(f: FilterState, keyword: string, location: string): SearchFilters {
  return {
    keyword,
    location,
    date_posted: f.datePosted,
    experience_levels: f.experienceLevels,
    remote_options: f.remoteOptions,
    platforms: f.platforms,
    max_jobs: f.maxJobs,
  }
}
