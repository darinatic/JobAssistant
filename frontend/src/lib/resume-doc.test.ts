import { describe, expect, it } from 'vitest'
import {
  type ResumeDoc,
  blankDoc,
  deserialize,
  hasContent,
  normalizeDoc,
  serialize,
  unreviewedCount,
} from './resume-doc'

const DOC: ResumeDoc = {
  version: 1,
  sections: [
    {
      id: 'contact',
      label: 'Contact',
      kind: 'fields',
      on: true,
      fields: [
        { label: 'Full name', value: 'Ng Tzun May' },
        { label: 'Email', value: 'tzunmay.ng@gmail.com' },
        { label: 'Phone', value: '+65 9123 4567' },
        { label: 'Location', value: 'Singapore' },
        { label: 'LinkedIn', value: 'https://linkedin.com/in/tzunmay' },
        { label: 'Portfolio', value: '' },
      ],
    },
    {
      id: 'summary',
      label: 'Summary',
      kind: 'text',
      on: true,
      text: 'Final-year Information Systems undergraduate with two internships.',
    },
    {
      id: 'skills',
      label: 'Skills',
      kind: 'chips',
      on: true,
      chips: [
        { text: 'Go', on: true },
        { text: 'Python', on: true },
        { text: 'COBOL', on: false },
      ],
    },
    {
      id: 'experience',
      label: 'Experience',
      kind: 'blocks',
      on: true,
      blocks: [
        {
          id: 'b1',
          on: true,
          title: 'Backend Engineering Intern',
          org: 'Endowus · Singapore',
          dates: 'JUN 2024 - PRESENT',
          bullets: [
            { id: 'l1', on: true, text: 'Rebuilt the rebalancing job in Go.' },
            { id: 'l2', on: false, text: 'Hidden bullet.' },
          ],
        },
        {
          id: 'b2',
          on: false,
          title: 'Teaching Assistant',
          org: 'NUS',
          dates: 'AUG 2023 - DEC 2023',
          bullets: [{ id: 'l3', on: true, text: 'Ran weekly labs.' }],
        },
      ],
    },
  ],
}

describe('serialize — contact header', () => {
  it('renders the name as the H1 and contact as one pipe-joined line', () => {
    const md = serialize(DOC)
    const lines = md.split('\n')
    expect(lines[0]).toBe('# Ng Tzun May')
    expect(lines[1]).toBe('') // blank line before the contact block
    expect(lines[2]).toBe(
      'tzunmay.ng@gmail.com | +65 9123 4567 | Singapore | linkedin.com/in/tzunmay',
    )
  })

  it('drops https:// from links and omits empty fields', () => {
    const md = serialize(DOC)
    expect(md).not.toContain('https://')
    expect(md).toContain('linkedin.com/in/tzunmay')
    // Portfolio was empty -> not present, no trailing separator
    expect(md).not.toMatch(/\|\s*$/m)
  })
})

describe('serialize — sections by kind', () => {
  it('renders a text section as a heading + paragraph', () => {
    const md = serialize(DOC)
    expect(md).toContain(
      '## Summary\n\nFinal-year Information Systems undergraduate with two internships.',
    )
  })

  it('renders skills as a flat comma line of enabled chips only', () => {
    const md = serialize(DOC)
    expect(md).toContain('## Skills\n\nGo, Python')
    expect(md).not.toContain('COBOL') // chip toggled off
  })

  it('folds org into the ### heading with a right-aligned date', () => {
    const md = serialize(DOC)
    expect(md).toContain('### Backend Engineering Intern, Endowus · Singapore | JUN 2024 - PRESENT')
  })

  it('emits enabled bullets as - lines and skips disabled ones', () => {
    const md = serialize(DOC)
    expect(md).toContain('- Rebuilt the rebalancing job in Go.')
    expect(md).not.toContain('Hidden bullet.')
  })
})

describe('serialize — contact is always the header', () => {
  it('emits the name H1 first even when contact is not the first section', () => {
    const reordered: ResumeDoc = {
      version: 1,
      sections: [DOC.sections[1], DOC.sections[0]], // summary before contact
    }
    const md = serialize(reordered)
    expect(md.split('\n')[0]).toBe('# Ng Tzun May')
  })
})

describe('serialize — include modes', () => {
  it("enabled mode drops sections/blocks that are off", () => {
    const md = serialize(DOC, { include: 'enabled' })
    expect(md).not.toContain('Teaching Assistant') // block.on === false
  })

  it('all mode keeps off blocks/bullets/chips (full master CV for search)', () => {
    const md = serialize(DOC, { include: 'all' })
    expect(md).toContain('Teaching Assistant')
    expect(md).toContain('Hidden bullet.')
    expect(md).toContain('COBOL')
  })
})

describe('serialize — reserved separator safety', () => {
  it('does not let a pipe inside a title corrupt the date split', () => {
    const doc: ResumeDoc = {
      version: 1,
      sections: [
        {
          id: 'experience',
          label: 'Experience',
          kind: 'blocks',
          on: true,
          blocks: [
            { id: 'b', on: true, title: 'Dev | Ops', org: '', dates: '2024', bullets: [] },
          ],
        },
      ],
    }
    const md = serialize(doc)
    // The only ' | ' in the heading must be the date separator.
    const heading = md.split('\n').find((l) => l.startsWith('### '))!
    expect(heading.split(' | ')).toHaveLength(2)
    expect(heading.endsWith(' | 2024')).toBe(true)
  })
})

describe('deserialize — round-trips our own canonical markdown', () => {
  it('recovers name, contact, and a role/bullet from serialized output', () => {
    const md = serialize(DOC, { include: 'enabled' })
    const back = deserialize(md)
    const contact = back.sections.find((s) => s.id === 'contact')!
    expect(contact.fields?.[0].value).toBe('Ng Tzun May')
    const exp = back.sections.find((s) => s.label === 'Experience')!
    expect(exp.blocks?.[0].title).toContain('Backend Engineering Intern')
    expect(exp.blocks?.[0].bullets[0].text).toBe('Rebuilt the rebalancing job in Go.')
  })

  it('parses the skills line into chips', () => {
    const back = deserialize('# A\n\na@b.com\n\n## Skills\n\nGo, Python, RAG\n')
    const skills = back.sections.find((s) => s.label === 'Skills')!
    expect(skills.kind).toBe('chips')
    expect(skills.chips?.map((c) => c.text)).toEqual(['Go', 'Python', 'RAG'])
  })
})

describe('normalizeDoc — the id-less parse response', () => {
  it('assigns ids to blocks and bullets and fills defaults', () => {
    const raw = {
      sections: [
        {
          id: 'experience', label: 'Experience', kind: 'blocks',
          blocks: [{ title: 'Eng', org: 'Acme', dates: '2023', bullets: [{ text: 'did x' }] }],
        },
      ],
    }
    const doc = normalizeDoc(raw)
    const block = doc.sections[0].blocks![0]
    expect(block.id).toBeTruthy()
    expect(block.on).toBe(true)
    expect(block.bullets[0].id).toBeTruthy()
    expect(block.bullets[0].on).toBe(true)
    expect(block.bullets[0].text).toBe('did x')
  })

  it('normalizes chips to {text, on} and drops empties', () => {
    const doc = normalizeDoc({ sections: [{ id: 'skills', label: 'Skills', kind: 'chips', chips: [{ text: 'Go' }, { text: '' }] }] })
    expect(doc.sections[0].chips).toEqual([{ text: 'Go', on: true }])
  })
})

describe('normalizeDoc — confidence + review flags (slice 2)', () => {
  it('carries conf/issue and starts unreviewed', () => {
    const doc = normalizeDoc({ sections: [{ id: 'summary', label: 'Summary', kind: 'text', text: 'x', conf: 0.7, issue: 'Mapped from Profile.' }] })
    const s = doc.sections[0]
    expect(s.conf).toBe(0.7)
    expect(s.issue).toBe('Mapped from Profile.')
    expect(s.reviewed).toBe(false)
  })

  it('defaults conf to 1 and issue to null when absent', () => {
    const doc = normalizeDoc({ sections: [{ id: 'skills', label: 'Skills', kind: 'chips', chips: [{ text: 'Go' }] }] })
    expect(doc.sections[0].conf).toBe(1)
    expect(doc.sections[0].issue).toBeNull()
  })
})

describe('unreviewedCount', () => {
  it('counts sections with an unresolved issue only', () => {
    const doc: ResumeDoc = {
      version: 1,
      sections: [
        { id: 'a', label: 'A', kind: 'text', on: true, text: '', issue: 'look', reviewed: false },
        { id: 'b', label: 'B', kind: 'text', on: true, text: '', issue: 'seen', reviewed: true },
        { id: 'c', label: 'C', kind: 'text', on: true, text: '', issue: null },
      ],
    }
    expect(unreviewedCount(doc)).toBe(1)
  })
})

describe('hasContent / blankDoc', () => {
  it('blankDoc has a name-less skeleton and reads as empty', () => {
    const doc = blankDoc()
    expect(hasContent(doc)).toBe(false)
  })

  it('a doc with a name reads as having content', () => {
    expect(hasContent(DOC)).toBe(true)
  })
})
