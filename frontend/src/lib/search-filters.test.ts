import { describe, expect, it } from 'vitest'
import { DEFAULT_FILTERS, restoreFilters, toRequestFilters } from './search-filters'

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

describe('board selection and native filters', () => {
  it('never sends a board-native filter that is not visible', () => {
    // Regression: selecting Careers@Gov, choosing an agency, then adding a second
    // board hid the panel but kept sending the agency filter. Results were silently
    // narrowed to GovTech with no control anywhere on screen saying so.
    const payload = toRequestFilters(
      {
        ...DEFAULT_FILTERS,
        platforms: [],  // "all boards" — no single board's panel is on screen
        platformFilters: { careersgov: { agencies: ['Government Technology Agency'] } },
      },
      'AI Engineer', 'Singapore',
    )
    expect(payload.platform_filters).toEqual({})
  })

  it('sends only the selected board native filters', () => {
    const payload = toRequestFilters(
      {
        ...DEFAULT_FILTERS,
        platforms: ['careersgov'],
        platformFilters: {
          careersgov: { agencies: ['Government Technology Agency'] },
          jobstreet: { work_types: ['full_time'] },
        },
      },
      'AI Engineer', 'Singapore',
    )
    expect(payload.platform_filters).toEqual({
      careersgov: { agencies: ['Government Technology Agency'] },
    })
  })

  it('keeps a board with no native filters set out of the payload', () => {
    const payload = toRequestFilters(
      { ...DEFAULT_FILTERS, platforms: ['linkedin'], platformFilters: {} },
      'AI Engineer', 'Singapore',
    )
    expect(payload.platform_filters).toEqual({})
  })
})

describe('restoreFilters', () => {
  it('clamps a multi-board selection saved by an older build', () => {
    const f = restoreFilters({ platforms: ['careersgov', 'jobstreet'] } as never)
    expect(f.platforms).toEqual(['careersgov'])
  })

  it('drops native filters belonging to a board that is no longer selected', () => {
    const f = restoreFilters({
      platforms: ['jobstreet'],
      platformFilters: {
        careersgov: { agencies: ['Government Technology Agency'] },
        jobstreet: { work_types: ['full_time'] },
      },
    } as never)
    expect(f.platformFilters).toEqual({ jobstreet: { work_types: ['full_time'] } })
  })

  it('fills in fields absent from older saved state', () => {
    const f = restoreFilters({ datePosted: 'past_week' } as never)
    expect(f.minSalary).toBeNull()
    expect(f.platformFilters).toEqual({})
    expect(f.maxJobs).toBe(25)
  })

  it('returns the defaults when nothing was saved', () => {
    expect(restoreFilters(undefined)).toEqual(DEFAULT_FILTERS)
  })
})
