// Page estimator — mirrors src/utils/page_budget.py. Keep the two in sync: the
// constants below are MEASURED, not guessed (scripts/calibrate_page_budget.py
// renders through the real Tectonic pipeline and reads the PDFs back).
//
// Density differs per template, so every constant is per template. Capacity sits at
// the conservative edge of the measured boundary band on purpose: over-reporting
// pages just makes the user trim a little more, while under-reporting promises
// "fits one page" and then hands back a two-page PDF.
export type Template = 'standard' | 'compact'

type Budget = {
  charsPerLine: number
  capacity: number
  target: number
  hName: number
  hSection: number
  hRole: number
}

// Calibrated 2026-08-12 against the retuned 10pt preambles.
const BUDGETS: Record<Template, Budget> = {
  standard: { charsPerLine: 119, capacity: 60, target: 57, hName: 2.5, hSection: 1.2, hRole: 1.11 },
  compact: { charsPerLine: 124, capacity: 64, target: 61, hName: 2.5, hSection: 1.14, hRole: 1.08 },
}

export const DEFAULT_TEMPLATE: Template = 'standard'

function budgetFor(template?: Template): Budget {
  return BUDGETS[template ?? DEFAULT_TEMPLATE] ?? BUDGETS[DEFAULT_TEMPLATE]
}

// A trailing page holding at most this many lines is an under-used remainder.
const _TRAILING_TRIM_MAX = 15

// Estimated rendered lines for the markdown (mirrors estimate_rendered_lines).
function estimateLines(md: string, template?: Template): number {
  const b = budgetFor(template)
  let lines = 0
  for (const raw of md.split('\n')) {
    const line = raw.trim()
    if (!line) continue
    if (line.startsWith('# ')) lines += b.hName
    else if (line.startsWith('## ')) lines += b.hSection
    else if (line.startsWith('### ')) lines += b.hRole
    else {
      const text = line.replace(/^[-*]\s+/, '').replace(/\*\*|\*|`|_/g, '').trim()
      lines += Math.max(1, Math.ceil(text.length / b.charsPerLine))
    }
  }
  return lines
}

export function estimatePageFit(md: string, template?: Template) {
  const b = budgetFor(template)
  const lines = estimateLines(md, template)
  return {
    pages: Math.max(1, Math.ceil(lines / b.capacity)),
    fits: lines <= b.capacity,
    overflow: Math.max(0, Math.ceil(lines - b.target)),
  }
}

// Mirrors src/utils/page_budget.py page_fit_target: recommend trimming a small
// remainder off an under-used trailing page, generalized to any page count.
export function estimatePageTarget(md: string, template?: Template) {
  const b = budgetFor(template)
  const lines = estimateLines(md, template)
  const pages = Math.max(1, Math.ceil(lines / b.capacity))
  const remainder = lines - (pages - 1) * b.capacity
  const underUsed = pages >= 2 && remainder <= _TRAILING_TRIM_MAX
  const targetPages = underUsed ? pages - 1 : pages
  return {
    pages,
    underUsedTrailingPage: underUsed,
    targetPages,
    targetLineBudget: underUsed ? targetPages * b.target : null,
    trimLines: underUsed ? Math.max(0, Math.ceil(lines - targetPages * b.target)) : 0,
  }
}
