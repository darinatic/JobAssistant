import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ReadoutRail, TOP_SKILLS, barFill } from './ReadoutRail'
import type { Insights } from '@/lib/api'

function insightsWith(n: number): Insights {
  return {
    job_count: 42,
    demanded_skills: Array.from({ length: n }, (_, i) => ({
      skill: `skill-${i}`, count: n - i, pct: 90 - i, candidate_has: i % 2 === 0,
    })),
    coverage: { avg_relevance: 61, strong_matches: 7 },
    salary: { min: 4000, max: 9000 },
  } as unknown as Insights
}

const noop = () => 'var(--ink)'

describe('ReadoutRail', () => {
  it('shows the top 10 demanded skills', () => {
    render(<ReadoutRail insights={insightsWith(20)} analyzing={false} scoreColor={noop} />)
    expect(TOP_SKILLS).toBe(10)
    expect(screen.getByText('skill-9')).toBeInTheDocument()
    expect(screen.queryByText('skill-10')).toBeNull()
  })

  it('shows every skill when fewer than ten are demanded', () => {
    render(<ReadoutRail insights={insightsWith(4)} analyzing={false} scoreColor={noop} />)
    expect(screen.getByText('skill-3')).toBeInTheDocument()
  })

  it('labels each bar so the state is available without colour', () => {
    render(<ReadoutRail insights={insightsWith(2)} analyzing={false} scoreColor={noop} />)
    expect(screen.getByTitle('in your cv')).toBeInTheDocument()
    expect(screen.getByTitle('gap to close')).toBeInTheDocument()
  })
})

describe('barFill', () => {
  it('fills an owned skill with a solid colour', () => {
    expect(barFill(true).background).toBe('var(--have)')
  })

  it('distinguishes a gap by TEXTURE as well as colour', () => {
    // The redundant cue is the point: colour alone fails for a colourblind
    // reader and in greyscale, so a gap bar must also be striped.
    expect(barFill(false).background).toContain('repeating-linear-gradient')
  })
})
