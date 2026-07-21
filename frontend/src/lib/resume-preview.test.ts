import { describe, it, expect } from 'vitest'
import { parseResume } from './resume-preview'

describe('parseResume', () => {
  it('parses name + contact across a blank line', () => {
    const blocks = parseResume('# Jane Tan\n\nAI Engineer · jane@x.com\n\n## Experience\n- Built RAG')
    expect(blocks[0]).toEqual({ kind: 'name', text: 'Jane Tan' })
    expect(blocks[1]).toEqual({ kind: 'contact', items: ['AI Engineer', 'jane@x.com'] })
    expect(blocks[2]).toEqual({ kind: 'section', text: 'Experience' })
    expect(blocks[3]).toEqual({ kind: 'bullets', items: ['Built RAG'] })
  })

  it('parses tight name+contact with no blank line', () => {
    const blocks = parseResume('# Jane Tan\nAI Engineer\n\n## X')
    expect(blocks[1]).toEqual({ kind: 'contact', items: ['AI Engineer'] })
  })

  it('does not absorb a section as contact when the name has none', () => {
    const blocks = parseResume('# Jane Tan\n\n## Experience\n- x')
    expect(blocks.find((b) => b.kind === 'contact')).toBeUndefined()
    expect(blocks[1]).toEqual({ kind: 'section', text: 'Experience' })
  })

  it('treats ### as a role and groups consecutive bullets', () => {
    const blocks = parseResume('### Acme — Engineer\n- a\n- b\nPlain line')
    expect(blocks[0]).toEqual({ kind: 'role', text: 'Acme — Engineer' })
    expect(blocks[1]).toEqual({ kind: 'bullets', items: ['a', 'b'] })
    expect(blocks[2]).toEqual({ kind: 'para', text: 'Plain line' })
  })

  it('splits a ### role heading on the LAST " | " into label + date', () => {
    const blocks = parseResume('### ML Engineer, Acme Corp | 2023 - Present')
    expect(blocks[0]).toEqual({ kind: 'role', text: 'ML Engineer, Acme Corp', date: '2023 - Present' })
  })

  it('leaves a ### role heading without " | " unchanged', () => {
    const blocks = parseResume('### Acme — Engineer')
    expect(blocks[0]).toEqual({ kind: 'role', text: 'Acme — Engineer' })
  })
})
