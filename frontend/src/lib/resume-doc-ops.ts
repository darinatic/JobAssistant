// Pure, immutable operations over a ResumeDoc. Each returns a new document and
// never mutates its input, so the builder hook can use them directly as setState
// updaters and chip/toggle state stays derivable.

import { type Block, type ResumeDoc, type Section, newId } from './resume-doc'

const clone = (doc: ResumeDoc): ResumeDoc => structuredClone(doc)

function edit(doc: ResumeDoc, sectionId: string, fn: (s: Section) => void): ResumeDoc {
  const next = clone(doc)
  const sec = next.sections.find((s) => s.id === sectionId)
  if (sec) fn(sec)
  return next
}

export function moveItem<T>(arr: T[], from: number, to: number): T[] {
  if (from === to || from < 0 || to < 0 || from >= arr.length || to >= arr.length) return arr.slice()
  const out = arr.slice()
  const [m] = out.splice(from, 1)
  out.splice(to, 0, m)
  return out
}

export function moveSection(doc: ResumeDoc, from: number, to: number): ResumeDoc {
  const next = clone(doc)
  next.sections = moveItem(next.sections, from, to)
  return next
}

export function toggleSectionOn(doc: ResumeDoc, sectionId: string): ResumeDoc {
  return edit(doc, sectionId, (s) => {
    s.on = !s.on
  })
}

// Confirm a parser-flagged section ("Looks right") — clears its nav flag.
export function resolveIssue(doc: ResumeDoc, sectionId: string): ResumeDoc {
  return edit(doc, sectionId, (s) => {
    s.reviewed = true
  })
}

export function setLabel(doc: ResumeDoc, sectionId: string, label: string): ResumeDoc {
  return edit(doc, sectionId, (s) => {
    s.label = label
  })
}

export function setField(doc: ResumeDoc, sectionId: string, idx: number, value: string): ResumeDoc {
  return edit(doc, sectionId, (s) => {
    if (s.fields?.[idx]) s.fields[idx].value = value
  })
}

export function setText(doc: ResumeDoc, sectionId: string, text: string): ResumeDoc {
  return edit(doc, sectionId, (s) => {
    s.text = text
  })
}

function freshBlock(withBullet: boolean): Block {
  return {
    id: newId('block'),
    on: true,
    title: '',
    org: '',
    startDate: '',
    endDate: '',
    current: false,
    bullets: withBullet ? [{ id: newId('bullet'), on: true, text: '' }] : [],
  }
}

export function addBlock(doc: ResumeDoc, sectionId: string, withBullet = true): ResumeDoc {
  return edit(doc, sectionId, (s) => {
    ;(s.blocks ??= []).push(freshBlock(withBullet))
  })
}

export function removeBlock(doc: ResumeDoc, sectionId: string, blockId: string): ResumeDoc {
  return edit(doc, sectionId, (s) => {
    if (s.blocks) s.blocks = s.blocks.filter((b) => b.id !== blockId)
  })
}

export function moveBlock(doc: ResumeDoc, sectionId: string, from: number, to: number): ResumeDoc {
  return edit(doc, sectionId, (s) => {
    if (s.blocks) s.blocks = moveItem(s.blocks, from, to)
  })
}

export function toggleBlockOn(doc: ResumeDoc, sectionId: string, blockId: string): ResumeDoc {
  return edit(doc, sectionId, (s) => {
    const b = s.blocks?.find((x) => x.id === blockId)
    if (b) b.on = !b.on
  })
}

function withBlock(
  doc: ResumeDoc,
  sectionId: string,
  blockId: string,
  fn: (b: Block) => void,
): ResumeDoc {
  return edit(doc, sectionId, (s) => {
    const b = s.blocks?.find((x) => x.id === blockId)
    if (b) fn(b)
  })
}

export function setBlockField(
  doc: ResumeDoc,
  sectionId: string,
  blockId: string,
  field: 'title' | 'org' | 'startDate' | 'endDate' | 'credential',
  value: string,
): ResumeDoc {
  return withBlock(doc, sectionId, blockId, (b) => {
    b[field] = value
  })
}

// "Currently here" toggle: turning it on clears the end date (renders "Present").
export function toggleBlockCurrent(doc: ResumeDoc, sectionId: string, blockId: string): ResumeDoc {
  return withBlock(doc, sectionId, blockId, (b) => {
    b.current = !b.current
    if (b.current) b.endDate = ''
  })
}

export function addBullet(doc: ResumeDoc, sectionId: string, blockId: string): ResumeDoc {
  return withBlock(doc, sectionId, blockId, (b) => {
    b.bullets.push({ id: newId('bullet'), on: true, text: '' })
  })
}

export function removeBullet(
  doc: ResumeDoc,
  sectionId: string,
  blockId: string,
  bulletId: string,
): ResumeDoc {
  return withBlock(doc, sectionId, blockId, (b) => {
    b.bullets = b.bullets.filter((l) => l.id !== bulletId)
  })
}

export function setBullet(
  doc: ResumeDoc,
  sectionId: string,
  blockId: string,
  bulletId: string,
  text: string,
): ResumeDoc {
  return withBlock(doc, sectionId, blockId, (b) => {
    const l = b.bullets.find((x) => x.id === bulletId)
    if (l) l.text = text
  })
}

export function toggleBulletOn(
  doc: ResumeDoc,
  sectionId: string,
  blockId: string,
  bulletId: string,
): ResumeDoc {
  return withBlock(doc, sectionId, blockId, (b) => {
    const l = b.bullets.find((x) => x.id === bulletId)
    if (l) l.on = !l.on
  })
}

export function addChip(doc: ResumeDoc, sectionId: string, text: string): ResumeDoc {
  const clean = text.trim()
  if (!clean) return doc
  return edit(doc, sectionId, (s) => {
    s.chips ??= []
    if (!s.chips.some((c) => c.text.toLowerCase() === clean.toLowerCase())) {
      s.chips.push({ text: clean, on: true })
    }
  })
}

export function removeChip(doc: ResumeDoc, sectionId: string, text: string): ResumeDoc {
  return edit(doc, sectionId, (s) => {
    if (s.chips) s.chips = s.chips.filter((c) => c.text.toLowerCase() !== text.toLowerCase())
  })
}

export function toggleChip(doc: ResumeDoc, sectionId: string, text: string): ResumeDoc {
  return edit(doc, sectionId, (s) => {
    const c = s.chips?.find((x) => x.text.toLowerCase() === text.toLowerCase())
    if (c) c.on = !c.on
  })
}
