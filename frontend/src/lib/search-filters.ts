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
  { value: 'careersgov', label: 'Careers@Gov' },
]
export const REMOTE_OPTIONS = [
  { value: 'on_site', label: 'On-site' },
  { value: 'remote', label: 'Remote' },
  { value: 'hybrid', label: 'Hybrid' },
]
export const MAX_JOBS_OPTIONS = [10, 25, 50, 100]
// Monthly SGD. 'any' plus the bands a candidate actually filters on.
export const SALARY_OPTIONS = [0, 3000, 4000, 5000, 6000, 8000]

export type FilterState = {
  datePosted: string
  experienceLevels: string[]
  remoteOptions: string[]
  platforms: string[]
  maxJobs: number
  minSalary: number | null
  // Board-native filters keyed by platform, e.g. { careersgov: { agencies: [...] } }.
  platformFilters: Record<string, Record<string, unknown>>
}

export const DEFAULT_FILTERS: FilterState = {
  datePosted: 'any',
  experienceLevels: [],
  remoteOptions: [],
  platforms: [],
  maxJobs: 25,
  minSalary: null,
  platformFilters: {},
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
    min_salary: f.minSalary,
    platform_filters: f.platformFilters,
  }
}
