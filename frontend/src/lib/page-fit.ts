// One-page estimator — mirrors src/utils/page_budget.py (calibrated against real
// Tectonic renders of the Roboto template: capacity 53 estimator-lines = one page).
const _CHARS_PER_LINE = 95, _PAGE_CAPACITY = 53, _PAGE_TARGET = 50
// A trailing page holding at most this many lines is an under-used remainder.
const _TRAILING_TRIM_MAX = 15

// Estimated rendered lines for the markdown (mirrors estimate_rendered_lines).
function estimateLines(md: string): number {
  let lines = 0
  for (const raw of md.split('\n')) {
    const line = raw.trim()
    if (!line) continue
    if (line.startsWith('# ')) lines += 2.5
    else if (line.startsWith('## ')) lines += 2.0
    else if (line.startsWith('### ')) lines += 1.3
    else {
      const text = line.replace(/^[-*]\s+/, '').replace(/\*\*|\*|`|_/g, '').trim()
      lines += Math.max(1, Math.ceil(text.length / _CHARS_PER_LINE))
    }
  }
  return lines
}

export function estimatePageFit(md: string) {
  const lines = estimateLines(md)
  return {
    pages: Math.max(1, Math.ceil(lines / _PAGE_CAPACITY)),
    fits: lines <= _PAGE_CAPACITY,
    overflow: Math.max(0, Math.ceil(lines - _PAGE_TARGET)),
  }
}

// Mirrors src/utils/page_budget.py page_fit_target: recommend trimming a small
// remainder off an under-used trailing page, generalized to any page count.
export function estimatePageTarget(md: string) {
  const lines = estimateLines(md)
  const pages = Math.max(1, Math.ceil(lines / _PAGE_CAPACITY))
  const remainder = lines - (pages - 1) * _PAGE_CAPACITY
  const underUsed = pages >= 2 && remainder <= _TRAILING_TRIM_MAX
  const targetPages = underUsed ? pages - 1 : pages
  return {
    pages,
    underUsedTrailingPage: underUsed,
    targetPages,
    targetLineBudget: underUsed ? targetPages * _PAGE_TARGET : null,
    trimLines: underUsed ? Math.max(0, Math.ceil(lines - targetPages * _PAGE_TARGET)) : 0,
  }
}
