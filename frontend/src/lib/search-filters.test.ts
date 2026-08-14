import { describe, expect, it } from 'vitest'
import { DEFAULT_FILTERS, toRequestFilters } from './search-filters'

describe('toRequestFilters', () => {
  it('builds the backend filters payload from control state + keyword/location', () => {
    const payload = toRequestFilters(
      { ...DEFAULT_FILTERS, datePosted: 'past_month', platforms: ['mycareersfuture'] },
      'Data Scientist', 'Singapore',
    )
    expect(payload).toEqual({
      keyword: 'Data Scientist', location: 'Singapore', date_posted: 'past_month',
      experience_levels: [], remote_options: [], platforms: ['mycareersfuture'], max_jobs: 25,
      min_salary: null, platform_filters: {},
    })
  })

  it('carries a salary floor and board-native filters through to the payload', () => {
    const payload = toRequestFilters(
      {
        ...DEFAULT_FILTERS,
        platforms: ['careersgov'],
        minSalary: 5000,
        platformFilters: { careersgov: { agencies: ['Government Technology Agency'] } },
      },
      'AI Engineer', 'Singapore',
    )
    expect(payload.min_salary).toBe(5000)
    expect(payload.platform_filters).toEqual({
      careersgov: { agencies: ['Government Technology Agency'] },
    })
  })
})
