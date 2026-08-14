// Shared app-level types, extracted from App.tsx.
import type { Job } from '@/lib/api'
import type { FilterState } from '@/lib/search-filters'

export type ActiveJob = { job?: Job; jd: string }
export type View = 'upload' | 'search' | 'job'
export type SavedSearch = { query?: string; interpreted?: Record<string, any> | null; jobs?: Job[]; filters?: FilterState }

// Tailoring styles + the one-line hint shown under the segmented control.
export const STYLES = [
  { key: 'faithful' as const, hint: 'Keep everything. Reorder and rephrase only, safest, nothing is cut.' },
  { key: 'aggressive' as const, hint: 'Restructure, cut low-relevance sections, hard one page. Maximum fit.' },
]
