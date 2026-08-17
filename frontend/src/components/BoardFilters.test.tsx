import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BoardFilters, SEARCHABLE_ABOVE } from './BoardFilters'
import type { Capabilities } from '@/lib/capabilities'

const CAPS: Capabilities = {
  boards: {},
  vocabularies: {
    careersgov_agencies: ['Government Technology Agency', 'Land Transport Authority'],
    careersgov_departments: ['Engineering'],
    careersgov_employment_types: ['Permanent'],
  },
}

// A vocabulary long enough to cross the threshold, like the real 96 agencies.
const MANY: Capabilities = {
  boards: {},
  vocabularies: {
    careersgov_agencies: Array.from({ length: 40 }, (_, i) => `Agency ${i}`),
    careersgov_departments: ['Engineering'],
    careersgov_employment_types: ['Permanent'],
  },
  aliases: { careersgov_agencies: { a7: 'Agency 7' } },
}

describe('BoardFilters', () => {
  it('renders a board its native filter rows', () => {
    render(<BoardFilters caps={CAPS} platform="careersgov" value={{}} onChange={vi.fn()} />)
    expect(screen.getByText('Government Technology Agency')).toBeInTheDocument()
    expect(screen.getByText('agency')).toBeInTheDocument()
  })

  it('renders nothing for a board with no native filters', () => {
    const { container } = render(
      <BoardFilters caps={CAPS} platform="linkedin" value={{}} onChange={vi.fn()} />,
    )
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing before capabilities load', () => {
    const { container } = render(
      <BoardFilters caps={null} platform="careersgov" value={{}} onChange={vi.fn()} />,
    )
    expect(container.firstChild).toBeNull()
  })

  it('adds a clicked value to the board filter payload', () => {
    const onChange = vi.fn()
    render(<BoardFilters caps={CAPS} platform="careersgov" value={{}} onChange={onChange} />)
    screen.getByText('Government Technology Agency').click()
    expect(onChange).toHaveBeenCalledWith({ agencies: ['Government Technology Agency'] })
  })

  it('removes an already-selected value', () => {
    const onChange = vi.fn()
    render(
      <BoardFilters caps={CAPS} platform="careersgov"
        value={{ agencies: ['Government Technology Agency'] }} onChange={onChange} />,
    )
    screen.getByText('Government Technology Agency').click()
    expect(onChange).toHaveBeenCalledWith({ agencies: [] })
  })

  it('renders a short vocabulary as chips, not a dropdown', () => {
    // For a handful of options, chips beat a dropdown: everything is visible at a
    // glance and selecting is one click.
    render(<BoardFilters caps={CAPS} platform="careersgov" value={{}} onChange={vi.fn()} />)
    expect(screen.getByText('Government Technology Agency')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /all 2/ })).toBeNull()
  })

  it('renders a long vocabulary as a searchable control', () => {
    render(<BoardFilters caps={MANY} platform="careersgov" value={{}} onChange={vi.fn()} />)
    expect(screen.getByRole('button', { name: /all 40/ })).toBeInTheDocument()
    // The 40 options are behind the control, not painted as a wall of chips.
    expect(screen.queryByText('Agency 7')).toBeNull()
  })

  it('puts the threshold where the real vocabularies fall either side of it', () => {
    // work type 4, employment type 6-8 -> chips; category 32, department 36,
    // agency 96 -> searchable.
    expect(SEARCHABLE_ABOVE).toBeGreaterThanOrEqual(8)
    expect(SEARCHABLE_ABOVE).toBeLessThan(32)
  })

  it('skips a row whose vocabulary is empty', () => {
    const caps: Capabilities = { boards: {}, vocabularies: { careersgov_agencies: ['GovTech'] } }
    render(<BoardFilters caps={caps} platform="careersgov" value={{}} onChange={vi.fn()} />)
    expect(screen.getByText('agency')).toBeInTheDocument()
    expect(screen.queryByText('function')).toBeNull()
  })
})
