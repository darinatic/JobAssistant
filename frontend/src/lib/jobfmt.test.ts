import { describe, it, expect } from 'vitest'
import type { Job } from './api'
import {
  formatSalary, salaryFull, postedLabel, experienceLabel, monthlySalary, jobTier,
  applyRefine, refineActive, EMPTY_REFINE, type RefineState,
} from './jobfmt'

const job = (over: Partial<Job> = {}): Job => ({
  platform: 'mycareersfuture', external_id: 'x', url: '#', title: 'T', company: 'C', location: 'SG', description: '', ...over,
})

describe('formatSalary (K units, keeps posted period)', () => {
  it('formats a monthly range', () => {
    expect(formatSalary(job({ salary_min: 8000, salary_max: 13500, salary_period: 'monthly' }))).toBe('$8K–13.5K/mo')
  })
  it('formats a long annual range compactly', () => {
    expect(formatSalary(job({ salary_min: 36000, salary_max: 100000, salary_period: 'annual' }))).toBe('$36K–100K/yr')
  })
  it('handles single bounds', () => {
    expect(formatSalary(job({ salary_max: 8000, salary_period: 'monthly' }))).toBe('Up to $8K/mo')
    expect(formatSalary(job({ salary_min: 5000, salary_period: 'monthly' }))).toBe('From $5K/mo')
  })
  it('omits the suffix when period is unknown; small numbers stay raw', () => {
    expect(formatSalary(job({ salary_min: 5000, salary_max: 7000 }))).toBe('$5K–7K')
    expect(formatSalary(job({ salary_min: 500, salary_max: 900, salary_period: 'monthly' }))).toBe('$500–900/mo')
  })
  it('falls back to salary_raw, else null', () => {
    expect(formatSalary(job({ salary_raw: 'Competitive' }))).toBe('Competitive')
    expect(formatSalary(job())).toBeNull()
  })
})

describe('salaryFull (tooltip)', () => {
  it('gives the exact figures', () => {
    expect(salaryFull(job({ salary_min: 36000, salary_max: 100000, salary_period: 'annual' }))).toBe('$36,000 – $100,000/yr')
  })
})

describe('postedLabel', () => {
  const NOW = Date.parse('2026-08-01T00:00:00Z')
  it('turns an ISO date into a relative age', () => {
    expect(postedLabel(job({ posted_date: '2026-08-01T00:00:00Z' }), NOW)).toBe('today')
    expect(postedLabel(job({ posted_date: '2026-07-29' }), NOW)).toBe('3d ago')
    expect(postedLabel(job({ posted_date: '2026-07-11' }), NOW)).toBe('3w ago')
    expect(postedLabel(job({ posted_date: '2026-05-01' }), NOW)).toBe('3mo ago')
  })
  it('normalizes board relative text', () => {
    expect(postedLabel(job({ posted_date: '2d ago' }), NOW)).toBe('2d ago')
    expect(postedLabel(job({ posted_date: '19h ago' }), NOW)).toBe('19h ago')
    expect(postedLabel(job({ posted_date: '3 days ago' }), NOW)).toBe('3d ago')
    expect(postedLabel(job({ posted_date: '1 month ago' }), NOW)).toBe('1mo ago')
    expect(postedLabel(job({ posted_date: '2 weeks ago' }), NOW)).toBe('2w ago')
  })
  it('null when absent', () => {
    expect(postedLabel(job(), NOW)).toBeNull()
  })
})

describe('experienceLabel', () => {
  it('maps normalized buckets, null when unknown', () => {
    expect(experienceLabel(job({ experience_level: 'mid_senior' }))).toBe('Mid-Senior')
    expect(experienceLabel(job({ experience_level: 'entry_level' }))).toBe('Entry')
    expect(experienceLabel(job({ experience_raw: 'Professional' }))).toBeNull()
    expect(experienceLabel(job())).toBeNull()
  })
})

describe('monthlySalary', () => {
  it('normalizes annual to monthly', () => {
    expect(monthlySalary(job({ salary_max: 120000, salary_period: 'annual' }))).toBe(10000)
    expect(monthlySalary(job({ salary_max: 8000, salary_period: 'monthly' }))).toBe(8000)
    expect(monthlySalary(job())).toBeNull()
  })
})

describe('jobTier', () => {
  const fits = [10, 20, 30, 40, 50, 60, 70, 80, 90]
  it('classifies by percentile + top-fit; unrated when no fit', () => {
    expect(jobTier(job({ fit: 90 }), fits)).toBe('top')
    expect(jobTier(job({ fit: 10 }), fits)).toBe('weak')
    expect(jobTier(job(), fits)).toBe('unrated')
  })
})

describe('applyRefine', () => {
  const fits = [10, 30, 50, 70, 90]
  const jobs = [
    job({ external_id: 'a', platform: 'linkedin', experience_level: 'mid_senior', salary_min: 8000, salary_max: 10000, salary_period: 'monthly', fit: 90 }),
    job({ external_id: 'b', platform: 'jobstreet', experience_level: 'entry_level', fit: 10 }),
    job({ external_id: 'c', platform: 'mycareersfuture', salary_min: 3000, salary_max: 4000, salary_period: 'monthly', fit: 50 }),
  ]
  const r = (o: Partial<RefineState>): RefineState => ({ ...EMPTY_REFINE, ...o })

  it('no-op when inactive', () => {
    expect(applyRefine(jobs, EMPTY_REFINE, fits)).toHaveLength(3)
    expect(refineActive(EMPTY_REFINE)).toBe(false)
  })
  it('filters by level', () => {
    expect(applyRefine(jobs, r({ levels: ['mid_senior'] }), fits).map((j) => j.external_id)).toEqual(['a'])
  })
  it('filters by platform', () => {
    expect(applyRefine(jobs, r({ platforms: ['jobstreet', 'mycareersfuture'] }), fits).map((j) => j.external_id)).toEqual(['b', 'c'])
  })
  it('filters by has-salary and min salary', () => {
    expect(applyRefine(jobs, r({ hasSalaryOnly: true }), fits).map((j) => j.external_id)).toEqual(['a', 'c'])
    expect(applyRefine(jobs, r({ minSalary: 5000 }), fits).map((j) => j.external_id)).toEqual(['a'])
  })
  it('filters by fit tier', () => {
    expect(applyRefine(jobs, r({ tiers: ['top'] }), fits).map((j) => j.external_id)).toEqual(['a'])
    expect(applyRefine(jobs, r({ tiers: ['unrated'] }), fits)).toHaveLength(0)
  })
})
