import { describe, it, expect } from 'vitest'
import { fitTier, isTopFit, fitLabel } from './fit'

const batch = [5, 8, 12, 20, 22, 30, 35, 40, 45, 52, 55, 60] // compressed spread

describe('fitTier', () => {
  it('buckets by percentile within the batch', () => {
    expect(fitTier(60, batch)).toBe('strong')
    expect(fitTier(5, batch)).toBe('weak')
    expect(fitTier(30, batch)).toBe('moderate')
  })

  it('calls a lone/near-empty result strong (no meaningful spread)', () => {
    expect(fitTier(42, [42])).toBe('strong')
    expect(fitTier(42, [40, 42])).toBe('strong')
  })
})

describe('isTopFit', () => {
  it('marks the top-N highest fits', () => {
    expect(isTopFit(60, batch, 3)).toBe(true)
    expect(isTopFit(55, batch, 3)).toBe(true)
    expect(isTopFit(20, batch, 3)).toBe(false)
  })
})

describe('fitLabel', () => {
  it('labels the highest as Top fit and the lowest as Weak fit', () => {
    expect(fitLabel(60, batch).label).toBe('Top fit')
    expect(fitLabel(5, batch).label).toBe('Weak fit')
  })
})
