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
    platform_filters: activeBoardFilters(f),
  }
}

/** The board-native filters that are actually on screen, and therefore the only
 *  ones it is honest to send.
 *
 *  Derived from the selection rather than read straight out of state: board panels
 *  only render for a single selected board, so returning the whole stored map made
 *  it possible to narrow results by a filter with no visible control anywhere. That
 *  is the same silent-filter failure the capability layer exists to prevent, so the
 *  payload is computed to make it unrepresentable rather than carefully managed.
 *
 *  Stored-but-inactive entries are kept in state on purpose: reselecting a board
 *  restores what you last chose for it, and it becomes visible again at the same
 *  moment it becomes active. */
export function activeBoardFilters(f: FilterState): Record<string, Record<string, unknown>> {
  if (f.platforms.length !== 1) return {}
  const board = f.platforms[0]
  const own = f.platformFilters[board]
  if (!own || Object.keys(own).length === 0) return {}
  return { [board]: own }
}

/** Restore saved filter state, normalised to what the current UI can represent.
 *
 *  `platforms` used to be a multi-select, so a returning visitor's localStorage can
 *  hold several boards. The board control is single-choice now, and rendering it
 *  would highlight only the first while the search still hit all of them: a hidden
 *  board with no control on screen. Clamp to the first, and drop native filters that
 *  no longer belong to the selected board. */
export function restoreFilters(saved: Partial<FilterState> | undefined): FilterState {
  const merged: FilterState = { ...DEFAULT_FILTERS, ...(saved ?? {}) }
  const platforms = Array.isArray(merged.platforms) ? merged.platforms.slice(0, 1) : []
  const board = platforms[0]
  return {
    ...merged,
    platforms,
    platformFilters:
      board && merged.platformFilters?.[board]
        ? { [board]: merged.platformFilters[board] }
        : {},
  }
}
