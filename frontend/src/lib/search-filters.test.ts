import { describe, expect, it } from 'vitest'
import { DEFAULT_FILTERS, filtersFromInterpreted, toRequestFilters } from './search-filters'

describe('filtersFromInterpreted', () => {
  it('maps an interpreted SearchQuery into control state', () => {
    const f = filtersFromInterpreted({
      keyword: 'AI Engineer', location: 'Singapore', date_posted: 'past_week',
      experience_levels: ['entry_level'], remote_options: ['remote'], platforms: ['linkedin'], max_jobs: 50,
    })
    expect(f).toEqual({
      datePosted: 'past_week', experienceLevels: ['entry_level'],
      remoteOptions: ['remote'], platforms: ['linkedin'], maxJobs: 50,
    })
  })

  it('falls back to defaults for missing fields', () => {
    expect(filtersFromInterpreted({ keyword: 'x' })).toEqual(DEFAULT_FILTERS)
  })
})

describe('toRequestFilters', () => {
  it('builds the backend filters payload from control state + keyword/location', () => {
    const payload = toRequestFilters(
      { datePosted: 'past_month', experienceLevels: [], remoteOptions: [], platforms: ['mycareersfuture'], maxJobs: 25 },
      'Data Scientist', 'Singapore',
    )
    expect(payload).toEqual({
      keyword: 'Data Scientist', location: 'Singapore', date_posted: 'past_month',
      experience_levels: [], remote_options: [], platforms: ['mycareersfuture'], max_jobs: 25,
    })
  })
})
