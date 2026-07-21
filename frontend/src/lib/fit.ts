// Relative fit presentation. The learned predictor's absolute scores are
// compressed (good AI/ML roles land ~30-55%), so it *ranks* well but a raw
// "N/100" misleads. We therefore show a job's fit RELATIVE to the current
// results — a tier plus a "top fit" marker — never the bare number.

export type FitTier = 'strong' | 'moderate' | 'weak'

// Cap on how many jobs get the "top fit" mark (the top ~15% of the batch,
// never more than this — so a big search still highlights a focused shortlist).
export const TOP_FIT_CAP = 10

// Default "top fit" count for a batch: top ~15%, capped, at least 1.
function topN(size: number): number {
  return Math.max(1, Math.min(TOP_FIT_CAP, Math.ceil(size * 0.15)))
}

// Tier a job's fit by its percentile within the current results' fit values.
export function fitTier(fit: number, allFits: number[]): FitTier {
  const sorted = [...allFits].sort((a, b) => a - b)
  if (sorted.length <= 2) return 'strong' // too few results for a meaningful spread
  const below = sorted.filter((f) => f < fit).length
  const pct = below / (sorted.length - 1)
  return pct >= 0.66 ? 'strong' : pct >= 0.33 ? 'moderate' : 'weak'
}

// True when `fit` is among the top fit values in the current results.
export function isTopFit(fit: number, allFits: number[], n: number = topN(allFits.length)): boolean {
  const top = [...allFits].sort((a, b) => b - a).slice(0, n)
  return top.length > 0 && fit >= top[top.length - 1]
}

// The label + semantic color token for a job's fit within the batch.
export function fitLabel(fit: number, allFits: number[]): { label: string; color: string } {
  if (isTopFit(fit, allFits)) return { label: 'Top fit', color: 'var(--have)' }
  const tier = fitTier(fit, allFits)
  if (tier === 'strong') return { label: 'Strong fit', color: 'var(--have)' }
  if (tier === 'moderate') return { label: 'Moderate fit', color: 'var(--primary)' }
  return { label: 'Weak fit', color: 'var(--gap)' }
}
