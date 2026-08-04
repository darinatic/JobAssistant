import { describe, expect, it } from 'vitest'
import { blankDoc, type ResumeDoc } from './resume-doc'
import {
  addBlock,
  addChip,
  moveSection,
  removeBlock,
  toggleBulletOn,
  toggleChip,
  setField,
} from './resume-doc-ops'

const base = (): ResumeDoc => ({
  version: 1,
  sections: [
    { id: 'contact', label: 'Contact', kind: 'fields', on: true, fields: [{ label: 'Full name', value: '' }] },
    { id: 'summary', label: 'Summary', kind: 'text', on: true, text: '' },
    {
      id: 'experience',
      label: 'Experience',
      kind: 'blocks',
      on: true,
      blocks: [
        { id: 'b1', on: true, title: 'A', org: '', dates: '', bullets: [{ id: 'l1', on: true, text: 'x' }] },
      ],
    },
    { id: 'skills', label: 'Skills', kind: 'chips', on: true, chips: [{ text: 'Go', on: true }] },
  ],
})

describe('moveSection', () => {
  it('reorders sections and does not mutate the input', () => {
    const doc = base()
    const out = moveSection(doc, 1, 3) // summary -> after skills
    expect(out.sections.map((s) => s.id)).toEqual(['contact', 'experience', 'skills', 'summary'])
    expect(doc.sections.map((s) => s.id)).toEqual(['contact', 'summary', 'experience', 'skills'])
  })
})

describe('toggleBulletOn', () => {
  it('flips a single bullet without touching siblings', () => {
    const out = toggleBulletOn(base(), 'experience', 'b1', 'l1')
    const bullet = out.sections.find((s) => s.id === 'experience')!.blocks![0].bullets[0]
    expect(bullet.on).toBe(false)
  })
})

describe('addBlock / removeBlock', () => {
  it('appends a fresh enabled block with one empty bullet', () => {
    const out = addBlock(base(), 'experience')
    const blocks = out.sections.find((s) => s.id === 'experience')!.blocks!
    expect(blocks).toHaveLength(2)
    expect(blocks[1].on).toBe(true)
    expect(blocks[1].bullets).toHaveLength(1)
    expect(blocks[1].bullets[0].text).toBe('')
  })

  it('removes a block by id', () => {
    const added = addBlock(base(), 'experience')
    const removed = removeBlock(added, 'experience', 'b1')
    expect(removed.sections.find((s) => s.id === 'experience')!.blocks!.map((b) => b.id)).not.toContain('b1')
  })
})

describe('chips', () => {
  it('toggleChip flips on/off', () => {
    const out = toggleChip(base(), 'skills', 'Go')
    expect(out.sections.find((s) => s.id === 'skills')!.chips![0].on).toBe(false)
  })

  it('addChip appends an enabled chip and is case-insensitively idempotent', () => {
    const once = addChip(base(), 'skills', 'Python')
    const twice = addChip(once, 'skills', 'python')
    expect(twice.sections.find((s) => s.id === 'skills')!.chips!.map((c) => c.text)).toEqual(['Go', 'Python'])
  })
})

describe('setField', () => {
  it('updates a contact field value immutably', () => {
    const doc = base()
    const out = setField(doc, 'contact', 0, 'Jane Doe')
    expect(out.sections[0].fields![0].value).toBe('Jane Doe')
    expect(doc.sections[0].fields![0].value).toBe('')
  })
})

describe('blankDoc integration', () => {
  it('can add a block to a blank experience section', () => {
    const out = addBlock(blankDoc(), 'experience')
    expect(out.sections.find((s) => s.id === 'experience')!.blocks).toHaveLength(1)
  })
})
