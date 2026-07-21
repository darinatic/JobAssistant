import { describe, it, expect } from 'vitest'
import { estimatePageFit, estimatePageTarget } from './page-fit'

const HEAD =
  '# Jane Candidate\ncontact line here\n## Summary\nShort summary line.\n' +
  '## Skills\nPython, PyTorch\n## Experience\n### ML Engineer, Acme (2023-2025)\n'
const BULLET =
  '- Built and shipped a production feature that improved a key metric by 30% for the platform\n'
const resume = (n: number) => HEAD + BULLET.repeat(n)

describe('estimatePageFit', () => {
  it('flags a short resume as one page', () => {
    const f = estimatePageFit(resume(20))
    expect(f.fits).toBe(true)
    expect(f.pages).toBe(1)
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
    const t = estimatePageTarget(resume(45))
    expect(t.pages).toBe(2)
    expect(t.underUsedTrailingPage).toBe(true)
    expect(t.targetPages).toBe(1)
    expect(t.targetLineBudget).toBe(50)
    expect(t.trimLines).toBeGreaterThan(0)
  })

  it('generalizes beyond one page (small spill onto page 3 -> trim to two)', () => {
    const t = estimatePageTarget(resume(100))
    expect(t.pages).toBe(3)
    expect(t.underUsedTrailingPage).toBe(true)
    expect(t.targetPages).toBe(2)
    expect(t.targetLineBudget).toBe(100)
  })

  it('leaves a well-used trailing page alone', () => {
    const t = estimatePageTarget(resume(80))
    expect(t.underUsedTrailingPage).toBe(false)
    expect(t.trimLines).toBe(0)
  })
})
