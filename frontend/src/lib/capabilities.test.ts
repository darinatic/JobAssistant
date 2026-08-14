import { describe, it, expect } from 'vitest'
import { filterSupport, droppedSummary, type Capabilities } from './capabilities'

const CAPS: Capabilities = {
  boards: {
    linkedin: {
      common: {
        date_posted: 'native', remote_options: 'unsupported',
        experience_levels: 'unsupported', min_salary: 'unsupported',
      },
      notes: { remote_options: 'The guest endpoint ignores f_WT (measured).' },
      native_filters: null,
    },
    jobstreet: {
      common: {
        date_posted: 'native', remote_options: 'native',
        experience_levels: 'unsupported', min_salary: 'native',
      },
      notes: {},
      native_filters: null,
    },
  },
  vocabularies: {},
}

describe('filterSupport', () => {
  it('is usable when any selected board can honour it', () => {
    expect(filterSupport(CAPS, ['linkedin', 'jobstreet'], 'remote_options').usable).toBe(true)
  })

  it('is unusable when no selected board can honour it', () => {
    const r = filterSupport(CAPS, ['linkedin'], 'remote_options')
    expect(r.usable).toBe(false)
    expect(r.reason).toContain('f_WT')
  })

  it('treats an empty board selection as every board', () => {
    expect(filterSupport(CAPS, [], 'remote_options').usable).toBe(true)
  })

  it('is usable when a board applies it locally', () => {
    const caps: Capabilities = {
      boards: {
        careersgov: { common: { experience_levels: 'local' }, notes: {}, native_filters: null },
      },
      vocabularies: {},
    }
    expect(filterSupport(caps, ['careersgov'], 'experience_levels').usable).toBe(true)
  })

  it('fails open while capabilities have not loaded', () => {
    expect(filterSupport(null, ['linkedin'], 'remote_options').usable).toBe(true)
  })

  it('falls back to a generic reason when a board gives none', () => {
    expect(filterSupport(CAPS, ['jobstreet'], 'experience_levels').reason).toBeTruthy()
  })
})

describe('droppedSummary', () => {
  it('names the board and the filter it ignored', () => {
    const s = droppedSummary({
      linkedin: { applied: ['date_posted'], dropped: { min_salary: 'ignores f_SB2' } },
    })
    expect(s).toContain('linkedin ignored min salary')
  })

  it('is empty when every filter was applied', () => {
    expect(droppedSummary({ jobstreet: { applied: ['min_salary'], dropped: {} } })).toBe('')
  })

  it('is empty before a search has run', () => {
    expect(droppedSummary(null)).toBe('')
  })
})
