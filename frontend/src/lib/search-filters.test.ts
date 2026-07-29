import { describe, expect, it } from 'vitest'
import { toRequestFilters } from './search-filters'

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
