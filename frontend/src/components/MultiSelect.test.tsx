import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MultiSelect, matchesQuery } from './MultiSelect'

const AGENCIES = [
  'Government Technology Agency',
  'Home Team Science and Technology Agency (HTX)',
  'Land Transport Authority',
  'Ministry of Manpower',
]
const ALIASES = {
  govtech: 'Government Technology Agency',
  htx: 'Home Team Science and Technology Agency (HTX)',
  mom: 'Ministry of Manpower',
}

describe('matchesQuery', () => {
  it('matches on a substring of the option', () => {
    expect(matchesQuery('Land Transport Authority', 'transport')).toBe(true)
  })

  it('is case insensitive', () => {
    expect(matchesQuery('Land Transport Authority', 'LAND')).toBe(true)
  })

  it('matches everything when the query is blank', () => {
    expect(matchesQuery('Anything', '   ')).toBe(true)
  })

  it('matches an acronym via the alias table', () => {
    // The board lists only full legal names, so without aliases "htx" finds nothing.
    expect(matchesQuery('Home Team Science and Technology Agency (HTX)', 'htx', ALIASES)).toBe(true)
    expect(matchesQuery('Government Technology Agency', 'govtech', ALIASES)).toBe(true)
  })

  it('does not let one option match another option alias', () => {
    expect(matchesQuery('Land Transport Authority', 'govtech', ALIASES)).toBe(false)
  })

  it('returns false for a genuine non-match', () => {
    expect(matchesQuery('Land Transport Authority', 'zzz', ALIASES)).toBe(false)
  })
})

describe('MultiSelect', () => {
  it('summarises the selection on the collapsed trigger', () => {
    render(<MultiSelect label="agency" options={AGENCIES} selected={['Ministry of Manpower']} onChange={vi.fn()} />)
    expect(screen.getByRole('button', { name: /1 selected/ })).toBeInTheDocument()
  })

  it('says how many options there are when nothing is selected', () => {
    render(<MultiSelect label="agency" options={AGENCIES} selected={[]} onChange={vi.fn()} />)
    expect(screen.getByRole('button', { name: /all 4/ })).toBeInTheDocument()
  })

  it('keeps selected values visible while collapsed', () => {
    // A filter that is active but invisible is the exact failure the capability
    // layer exists to prevent; collapsing the panel must not recreate it.
    render(<MultiSelect label="agency" options={AGENCIES} selected={['Ministry of Manpower']} onChange={vi.fn()} />)
    expect(screen.getByTitle('remove Ministry of Manpower')).toBeInTheDocument()
  })

  it('removes a value when its chip is clicked', async () => {
    const onChange = vi.fn()
    render(<MultiSelect label="agency" options={AGENCIES} selected={['Ministry of Manpower']} onChange={onChange} />)
    await userEvent.click(screen.getByTitle('remove Ministry of Manpower'))
    expect(onChange).toHaveBeenCalledWith([])
  })

  it('filters the list as you type, including by acronym', async () => {
    render(<MultiSelect label="agency" options={AGENCIES} selected={[]} onChange={vi.fn()} aliases={ALIASES} />)
    await userEvent.click(screen.getByRole('button', { name: /all 4/ }))
    await userEvent.type(screen.getByPlaceholderText(/search 4 agency/), 'htx')
    expect(screen.getByText('Home Team Science and Technology Agency (HTX)')).toBeInTheDocument()
    expect(screen.queryByText('Land Transport Authority')).toBeNull()
  })

  it('adds a value when an option is clicked', async () => {
    const onChange = vi.fn()
    render(<MultiSelect label="agency" options={AGENCIES} selected={[]} onChange={onChange} />)
    await userEvent.click(screen.getByRole('button', { name: /all 4/ }))
    await userEvent.click(screen.getByText('Land Transport Authority'))
    expect(onChange).toHaveBeenCalledWith(['Land Transport Authority'])
  })

  it('tells you when nothing matches instead of showing an empty panel', async () => {
    render(<MultiSelect label="agency" options={AGENCIES} selected={[]} onChange={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /all 4/ }))
    await userEvent.type(screen.getByPlaceholderText(/search 4 agency/), 'zzzz')
    expect(screen.getByText(/no match for/)).toBeInTheDocument()
  })

  it('closes on Escape', async () => {
    render(<MultiSelect label="agency" options={AGENCIES} selected={[]} onChange={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /all 4/ }))
    expect(screen.getByPlaceholderText(/search 4 agency/)).toBeInTheDocument()
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByPlaceholderText(/search 4 agency/)).toBeNull()
  })
})
