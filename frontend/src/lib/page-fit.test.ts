import { describe, it, expect } from 'vitest'
import { estimatePageFit, estimatePageTarget } from './page-fit'

// These mirror tests/test_page_budget.py. The two estimators must agree, or the
// live page badge disagrees with the budget the backend hands the tailor.
const HEAD =
  '# Jane Candidate\ncontact line here\n## Summary\nShort summary line.\n' +
  '## Skills\nPython, PyTorch\n## Experience\n### ML Engineer, Acme (2023-2025)\n'
const BULLET =
  '- Built and shipped a production feature that improved a key metric by 30% for the platform\n'
const resume = (n: number) => HEAD + BULLET.repeat(n)

const STANDARD_TARGET = 57
const COMPACT_TARGET = 61

describe('estimatePageFit', () => {
  it('flags a short resume as one page', () => {
    const f = estimatePageFit(resume(20))
    expect(f.fits).toBe(true)
    expect(f.pages).toBe(1)
  })

  it('matches the calibrated boundary for the standard template', () => {
    expect(estimatePageFit(resume(45)).fits).toBe(true)
    expect(estimatePageFit(resume(50)).fits).toBe(false)
  })

  it('fits more on a page in the compact template', () => {
    const md = resume(50)
    expect(estimatePageFit(md, 'standard').pages).toBe(2)
    expect(estimatePageFit(md, 'compact').pages).toBe(1)
  })

  it('defaults to the standard template', () => {
    const md = resume(50)
    expect(estimatePageFit(md)).toEqual(estimatePageFit(md, 'standard'))
  })
})

describe('estimatePageTarget', () => {
  it('recommends no trim for a solid one-page resume', () => {
    const t = estimatePageTarget(resume(20))
    expect(t.pages).toBe(1)
    expect(t.underUsedTrailingPage).toBe(false)
    expect(t.targetPages).toBe(1)
    expect(t.trimLines).toBe(0)
    expect(t.targetLineBudget).toBeNull()
  })

  it('recommends trimming a small spill onto page 2 down to one page', () => {
    const t = estimatePageTarget(resume(50))
    expect(t.pages).toBe(2)
    expect(t.underUsedTrailingPage).toBe(true)
    expect(t.targetPages).toBe(1)
    expect(t.targetLineBudget).toBe(STANDARD_TARGET)
    expect(t.trimLines).toBeGreaterThan(0)
  })

  it('generalizes beyond one page (small spill onto page 3 -> trim to two)', () => {
    const t = estimatePageTarget(resume(120))
    expect(t.pages).toBe(3)
    expect(t.underUsedTrailingPage).toBe(true)
    expect(t.targetPages).toBe(2)
    expect(t.targetLineBudget).toBe(2 * STANDARD_TARGET)
  })

  it('leaves a well-used trailing page alone', () => {
    const t = estimatePageTarget(resume(80))
    expect(t.underUsedTrailingPage).toBe(false)
    expect(t.trimLines).toBe(0)
  })

  it('budgets against the requested template', () => {
    expect(estimatePageTarget(resume(50), 'standard').targetLineBudget).toBe(STANDARD_TARGET)
    expect(estimatePageTarget(resume(55), 'compact').targetLineBudget).toBe(COMPACT_TARGET)
    expect(COMPACT_TARGET).toBeGreaterThan(STANDARD_TARGET)
  })
})
