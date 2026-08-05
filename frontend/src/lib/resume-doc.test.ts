import { describe, expect, it } from 'vitest'
import {
  type ResumeDoc,
  blankDoc,
  deserialize,
  fromMonthInput,
  hasContent,
  normalizeDoc,
  serialize,
  splitDateRange,
  toMonthInput,
  unreviewedCount,
  upgradeDoc,
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
          startDate: '06/2024',
          endDate: '',
          current: true,
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
          startDate: '08/2023',
          endDate: '12/2023',
          current: false,
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
    expect(md).toContain('### Backend Engineering Intern, Endowus · Singapore | 06/2024 - Present')
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
            { id: 'b', on: true, title: 'Dev | Ops', org: '', startDate: '2024', endDate: '', current: false, bullets: [] },
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

describe('date helpers (block dates split into start/end/current)', () => {
  it('splits a range and normalizes months to MM/YYYY', () => {
    expect(splitDateRange('Jun 2024 - Aug 2024')).toEqual({ startDate: '06/2024', endDate: '08/2024', current: false })
  })
  it('detects Present/Current as the "current" flag and clears the end', () => {
    expect(splitDateRange('09/2025 - Present')).toEqual({ startDate: '09/2025', endDate: '', current: true })
    expect(splitDateRange('Mar 2023 – current')).toEqual({ startDate: '03/2023', endDate: '', current: true })
  })
  it('keeps year-only or unparseable parts verbatim', () => {
    expect(splitDateRange('2022 - 2026')).toEqual({ startDate: '2022', endDate: '2026', current: false })
    expect(splitDateRange('Summer 2024')).toEqual({ startDate: 'Summer 2024', endDate: '', current: false })
  })
  it('handles a single date and an empty string', () => {
    expect(splitDateRange('Mar 2025')).toEqual({ startDate: '03/2025', endDate: '', current: false })
    expect(splitDateRange('')).toEqual({ startDate: '', endDate: '', current: false })
  })
  it('round-trips the month-input <-> MM/YYYY format', () => {
    expect(toMonthInput('06/2024')).toBe('2024-06')
    expect(toMonthInput('Jun 2024')).toBe('2024-06')
    expect(toMonthInput('2022')).toBe('') // year-only can't map to a month
    expect(fromMonthInput('2024-06')).toBe('06/2024')
  })
})

describe('serialize — date range from start/end/current', () => {
  const block = (over: Partial<import('./resume-doc').Block>) => ({
    version: 1 as const,
    sections: [{
      id: 'experience', label: 'Experience', kind: 'blocks' as const, on: true,
      blocks: [{ id: 'b', on: true, title: 'Eng', org: 'Acme', startDate: '', endDate: '', current: false, bullets: [], ...over }],
    }],
  })
  const heading = (doc: ResumeDoc) => serialize(doc).split('\n').find((l) => l.startsWith('### '))!

  it('renders start - Present when current', () => {
    expect(heading(block({ startDate: '06/2024', current: true }))).toBe('### Eng, Acme | 06/2024 - Present')
  })
  it('renders start - end when both set', () => {
    expect(heading(block({ startDate: '06/2022', endDate: '05/2024' }))).toBe('### Eng, Acme | 06/2022 - 05/2024')
  })
  it('renders start alone when there is no end', () => {
    expect(heading(block({ startDate: '03/2025' }))).toBe('### Eng, Acme | 03/2025')
  })
})

describe('normalizeDoc + upgradeDoc — dates', () => {
  it('normalizeDoc splits the parser dates string into start/end/current', () => {
    const doc = normalizeDoc({ sections: [{ id: 'experience', label: 'Experience', kind: 'blocks', blocks: [{ title: 'Eng', org: 'Acme', dates: 'Jun 2024 - Present' }] }] })
    const b = doc.sections[0].blocks![0]
    expect(b.startDate).toBe('06/2024')
    expect(b.current).toBe(true)
  })
  it('upgradeDoc migrates a legacy block that still has a `dates` string', () => {
    const legacy = { version: 1, sections: [{ id: 'experience', label: 'Experience', kind: 'blocks', on: true, blocks: [{ id: 'b', on: true, title: 'Eng', org: 'Acme', dates: '2022 - 2026', bullets: [] }] }] } as unknown as ResumeDoc
    const b = upgradeDoc(legacy).sections[0].blocks![0]
    expect(b.startDate).toBe('2022')
    expect(b.endDate).toBe('2026')
    expect(b.current).toBe(false)
    expect((b as Record<string, unknown>).dates).toBeUndefined()
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
