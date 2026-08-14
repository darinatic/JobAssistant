import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BoardFilters } from './BoardFilters'
import type { Capabilities } from '@/lib/capabilities'

const CAPS: Capabilities = {
  boards: {},
  vocabularies: {
    careersgov_agencies: ['Government Technology Agency', 'Land Transport Authority'],
    careersgov_departments: ['Engineering'],
    careersgov_employment_types: ['Permanent'],
  },
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

  it('skips a row whose vocabulary is empty', () => {
    const caps: Capabilities = { boards: {}, vocabularies: { careersgov_agencies: ['GovTech'] } }
    render(<BoardFilters caps={caps} platform="careersgov" value={{}} onChange={vi.fn()} />)
    expect(screen.getByText('agency')).toBeInTheDocument()
    expect(screen.queryByText('function')).toBeNull()
  })
})
