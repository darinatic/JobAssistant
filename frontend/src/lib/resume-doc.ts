// The structured resume model that backs the builder. It is the client's source
// of truth (localStorage); every backend call receives its serialization to the
// app's canonical markdown contract, so the backend never learns it exists.
//
// Canonical markdown contract (see src/utils/latex_renderer.py + the tailor
// prompt in src/agents/resume_tailor.py):
//   # Name                              -> H1, centered
//   <blank>                             -> the "skip one blank line" rule
//   a@b.com | +65 ... | linkedin.com/x  -> ONE contact line, https:// dropped
//   ## Section
//   ### Title, Org | Dates              -> company INSIDE the heading, date last
//   - bullet
//   Go, Python, RAG                     -> Skills as a flat comma line

export type FieldKV = { label: string; value: string }
export type Chip = { text: string; on: boolean }
export type Bullet = { id: string; on: boolean; text: string }
export type Block = {
  id: string
  on: boolean
  title: string
  org: string
  startDate: string       // MM/YYYY (or as written when not a clean month)
  endDate: string         // MM/YYYY; empty when `current`
  current: boolean        // "still here" → renders the end as "Present"
  credential?: string
  bullets: Bullet[]
}
export type SectionKind = 'fields' | 'text' | 'chips' | 'blocks'
export type Section = {
  id: string
  label: string
  kind: SectionKind
  on: boolean
  conf?: number          // 0..1 parse confidence (slice 2)
  issue?: string | null  // review prompt from the parser, null/absent when clean
  reviewed?: boolean      // user confirmed the issue ("Looks right")
  fields?: FieldKV[]
  text?: string
  chips?: Chip[]
  blocks?: Block[]
}
export type ResumeDoc = { version: 1; sections: Section[] }

export type SerializeOpts = { include?: 'all' | 'enabled' }

let _seq = 0
export function newId(prefix: string): string {
  return `${prefix}-${(_seq++).toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

const dropScheme = (v: string) => v.replace(/^https?:\/\//i, '')
const isNameLabel = (label: string) => /name/i.test(label)
// ' | ' is the reserved date separator (the renderer rpartitions on the LAST
// one). Strip any stray pipe from a non-date segment so it can't be mistaken
// for the date boundary.
const noPipe = (v: string) => v.replace(/\s*\|\s*/g, ' / ').trim()

// ---- block dates: MM/YYYY <-> native month-input, and range parsing ----

const _MONTHS: Record<string, string> = {
  jan: '01', january: '01', feb: '02', february: '02', mar: '03', march: '03',
  apr: '04', april: '04', may: '05', jun: '06', june: '06', jul: '07', july: '07',
  aug: '08', august: '08', sep: '09', sept: '09', september: '09', oct: '10', october: '10',
  nov: '11', november: '11', dec: '12', december: '12',
}

// A stored date -> "YYYY-MM" for <input type="month">; '' when it isn't a clean month.
export function toMonthInput(s: string): string {
  const t = (s ?? '').trim()
  let m: RegExpExecArray | null
  if ((m = /^(\d{4})-(\d{2})$/.exec(t))) return t
  if ((m = /^(\d{1,2})\/(\d{4})$/.exec(t))) return `${m[2]}-${m[1].padStart(2, '0')}`
  if ((m = /^([A-Za-z]+)\.?\s+(\d{4})$/.exec(t))) {
    const mm = _MONTHS[m[1].toLowerCase()]
    if (mm) return `${m[2]}-${mm}`
  }
  return ''
}

// "YYYY-MM" (month input) -> "MM/YYYY".
export function fromMonthInput(v: string): string {
  const m = /^(\d{4})-(\d{2})$/.exec((v ?? '').trim())
  return m ? `${m[2]}/${m[1]}` : ''
}

// Normalize a single date to MM/YYYY when we can, else keep it verbatim.
function normMonth(s: string): string {
  const mi = toMonthInput(s)
  return mi ? fromMonthInput(mi) : (s ?? '').trim()
}

// Parse a free-form date range ("Jun 2024 - Present", "2022 – 2026") into fields.
export function splitDateRange(s: string): { startDate: string; endDate: string; current: boolean } {
  const raw = (s ?? '').trim()
  if (!raw) return { startDate: '', endDate: '', current: false }
  const parts = raw.split(/\s*[–—]\s*|\s+-\s+|\s+to\s+/i)
  const rawEnd = (parts[1] ?? '').trim()
  const current = /present|current|now|ongoing|to date|till date/i.test(rawEnd)
  return {
    startDate: normMonth(parts[0] ?? ''),
    endDate: current ? '' : normMonth(rawEnd),
    current,
  }
}

// Fields -> the trailing "date" segment of the ### heading.
function dateRange(b: Block): string {
  const s = (b.startDate ?? '').trim()
  const e = (b.endDate ?? '').trim()
  if (b.current) return s ? `${s} - Present` : 'Present'
  if (s && e) return `${s} - ${e}`
  return s || e || ''
}

function roleHeading(b: Block): string {
  const orgPart = [noPipe(b.org), b.credential ? noPipe(b.credential) : '']
    .filter(Boolean)
    .join(' · ')
  let h = noPipe(b.title)
  if (orgPart) h += `, ${orgPart}`
  const dates = dateRange(b)
  if (dates) h += ` | ${dates}`
  return h
}

function sectionBody(sec: Section, all: boolean): string {
  if (sec.kind === 'text') return (sec.text ?? '').trim()
  if (sec.kind === 'chips') {
    return (sec.chips ?? [])
      .filter((c) => (all || c.on) && c.text.trim())
      .map((c) => c.text.trim())
      .join(', ')
  }
  if (sec.kind === 'blocks') {
    const blocks = (sec.blocks ?? []).filter((b) => all || b.on)
    const chunks = blocks
      .map((b) => {
        const bullets = (b.bullets ?? [])
          .filter((l) => (all || l.on) && l.text.trim())
          .map((l) => `- ${l.text.trim()}`)
        const head = `### ${roleHeading(b)}`
        return bullets.length ? `${head}\n${bullets.join('\n')}` : head
      })
      .filter(Boolean)
    return chunks.join('\n\n')
  }
  return ''
}

export function serialize(doc: ResumeDoc, opts: SerializeOpts = {}): string {
  const all = opts.include === 'all'
  const chunks: string[] = []

  // Contact must serialize to the header (first line) regardless of its position
  // in the section list — the user can drag it anywhere in the nav.
  const contact = doc.sections.find((s) => s.kind === 'fields' && s.id === 'contact')
  const ordered = contact ? [contact, ...doc.sections.filter((s) => s !== contact)] : doc.sections

  for (const sec of ordered) {
    if (sec.kind === 'fields' && sec.id === 'contact') {
      const fields = sec.fields ?? []
      const name = fields.find((f) => isNameLabel(f.label))?.value.trim() ?? ''
      const rest = fields
        .filter((f) => !isNameLabel(f.label))
        .map((f) => dropScheme(f.value.trim()))
        .filter(Boolean)
      chunks.push(rest.length ? `# ${name}\n\n${rest.join(' | ')}` : `# ${name}`)
      continue
    }
    if (!all && !sec.on) continue
    const body = sectionBody(sec, all)
    if (!body) continue
    chunks.push(`## ${sec.label}\n\n${body}`)
  }

  return `${chunks.join('\n\n')}\n`
}

// ---- deterministic reverse parser (our own canonical markdown -> ResumeDoc) ----
// Best-effort: forward serialization is lossless, but the "### Title, Org"
// heading can't always be split unambiguously back into title/org (a title may
// contain a comma). Used for one-time migration of a legacy overlap.cv.

const SKILLS_RE = /skills?/i

function classifyContact(item: string): string {
  if (item.includes('@')) return 'Email'
  if (/^[+(]?\d[\d\s()-]{5,}$/.test(item)) return 'Phone'
  if (/\.[a-z]{2,}/i.test(item) || /linkedin|github/i.test(item)) {
    return /linkedin/i.test(item) ? 'LinkedIn' : 'Portfolio'
  }
  return 'Location'
}

export function deserialize(md: string): ResumeDoc {
  const lines = (md ?? '').replace(/\r\n/g, '\n').split('\n')
  const sections: Section[] = []
  let i = 0
  while (i < lines.length && !lines[i].trim()) i++

  // Header: name + contact line.
  const contactFields: FieldKV[] = [{ label: 'Full name', value: '' }]
  if (i < lines.length && lines[i].startsWith('# ')) {
    contactFields[0].value = lines[i].slice(2).trim()
    i++
    if (
      i + 1 < lines.length && !lines[i].trim() &&
      lines[i + 1].trim() && !lines[i + 1].startsWith('#')
    ) {
      i++
    }
    while (i < lines.length && lines[i].trim() && !lines[i].startsWith('#')) {
      for (const raw of lines[i].split('|')) {
        const item = raw.trim()
        if (item) contactFields.push({ label: classifyContact(item), value: item })
      }
      i++
    }
  }
  sections.push({ id: 'contact', label: 'Contact', kind: 'fields', on: true, fields: contactFields })

  // Body sections.
  let cur: Section | null = null
  let curBlock: Block | null = null
  const paras: string[] = []

  const flushText = () => {
    if (cur && cur.kind === 'text' && paras.length) {
      cur.text = paras.join('\n\n')
    }
    paras.length = 0
  }
  const closeSection = () => {
    flushText()
    if (cur) sections.push(cur)
    cur = null
    curBlock = null
  }

  for (; i < lines.length; i++) {
    const s = lines[i].trim()
    if (!s) continue
    if (s.startsWith('## ')) {
      closeSection()
      const label = s.slice(3).trim()
      const kind: SectionKind = SKILLS_RE.test(label) ? 'chips' : 'text'
      cur = { id: label.toLowerCase().replace(/[^a-z0-9]+/g, '-'), label, kind, on: true }
      if (kind === 'chips') cur.chips = []
      if (kind === 'text') cur.text = ''
    } else if (s.startsWith('### ')) {
      if (!cur) continue
      if (cur.kind !== 'blocks') {
        cur.kind = 'blocks'
        cur.blocks = []
        delete cur.text
      }
      const heading = s.slice(4).trim()
      const p = heading.lastIndexOf(' | ')
      const dates = p === -1 ? '' : heading.slice(p + 3).trim()
      const left = p === -1 ? heading : heading.slice(0, p).trim()
      const comma = left.indexOf(', ')
      const title = comma === -1 ? left : left.slice(0, comma).trim()
      const org = comma === -1 ? '' : left.slice(comma + 2).trim()
      curBlock = { id: newId('block'), on: true, title, org, ...splitDateRange(dates), bullets: [] }
      cur.blocks!.push(curBlock)
    } else if (/^[-*+]\s+/.test(s)) {
      const text = s.replace(/^[-*+]\s+/, '').trim()
      if (curBlock) curBlock.bullets.push({ id: newId('bullet'), on: true, text })
    } else if (cur && cur.kind === 'chips') {
      for (const c of s.split(',')) {
        const text = c.trim()
        if (text) cur.chips!.push({ text, on: true })
      }
    } else if (cur && cur.kind === 'text') {
      paras.push(s)
    }
  }
  closeSection()

  return { version: 1, sections }
}

// Turn the backend parse response (sections with no block/bullet ids) into a
// valid ResumeDoc, assigning ids and filling defaults. Defensive against a
// partial/loose payload.
export function normalizeDoc(raw: unknown): ResumeDoc {
  const r = raw as { sections?: unknown[] } | null
  const kinds: SectionKind[] = ['fields', 'text', 'chips', 'blocks']
  const sections: Section[] = (r?.sections ?? []).map((raw): Section => {
    const s = raw as Record<string, any>
    const kind: SectionKind = kinds.includes(s.kind) ? s.kind : 'text'
    const sec: Section = {
      id: String(s.id ?? newId('sec')),
      label: String(s.label ?? ''),
      kind,
      on: s.on !== false,
      conf: typeof s.conf === 'number' ? s.conf : 1,
      issue: s.issue ? String(s.issue) : null,
      reviewed: false,
    }
    if (kind === 'fields') {
      sec.fields = (s.fields ?? []).map((f: any) => ({
        label: String(f.label ?? ''),
        value: String(f.value ?? ''),
      }))
    } else if (kind === 'text') {
      sec.text = String(s.text ?? '')
    } else if (kind === 'chips') {
      sec.chips = (s.chips ?? [])
        .map((c: any) => ({ text: String(c.text ?? '').trim(), on: c.on !== false }))
        .filter((c: Chip) => c.text)
    } else {
      sec.blocks = (s.blocks ?? []).map((b: any): Block => ({
        id: newId('block'),
        on: b.on !== false,
        title: String(b.title ?? ''),
        org: String(b.org ?? ''),
        ...splitDateRange(String(b.dates ?? '')),
        credential: b.credential ? String(b.credential) : undefined,
        bullets: (b.bullets ?? []).map((l: any) => ({
          id: newId('bullet'),
          on: l.on !== false,
          text: String(l.text ?? ''),
        })),
      }))
    }
    return sec
  })
  return { version: 1, sections }
}

// Upgrade a doc loaded from localStorage that predates split dates: turn any
// legacy block `dates` string into startDate/endDate/current in place.
export function upgradeDoc(doc: ResumeDoc): ResumeDoc {
  for (const sec of doc.sections) {
    if (sec.kind !== 'blocks') continue
    for (const b of sec.blocks ?? []) {
      const legacy = b as unknown as { dates?: string; startDate?: string }
      if (legacy.startDate === undefined) {
        Object.assign(b, splitDateRange(legacy.dates ?? ''))
        delete legacy.dates
      } else {
        b.startDate ??= ''
        b.endDate ??= ''
        b.current ??= false
      }
    }
  }
  return doc
}

// Sections the parser flagged that the user hasn't confirmed yet (slice 2).
export function unreviewedCount(doc: ResumeDoc): number {
  return doc.sections.filter((s) => s.issue && !s.reviewed).length
}

export function hasContent(doc: ResumeDoc): boolean {
  for (const sec of doc.sections) {
    if (sec.kind === 'fields') {
      if ((sec.fields ?? []).some((f) => isNameLabel(f.label) && f.value.trim())) return true
      continue
    }
    if (sec.kind === 'text' && (sec.text ?? '').trim()) return true
    if (sec.kind === 'chips' && (sec.chips ?? []).some((c) => c.text.trim())) return true
    if (sec.kind === 'blocks') {
      for (const b of sec.blocks ?? []) {
        if (b.title.trim() || b.org.trim() || b.bullets.some((l) => l.text.trim())) return true
      }
    }
  }
  return false
}

export function blankDoc(): ResumeDoc {
  return {
    version: 1,
    sections: [
      {
        id: 'contact',
        label: 'Contact',
        kind: 'fields',
        on: true,
        fields: [
          { label: 'Full name', value: '' },
          { label: 'Email', value: '' },
          { label: 'Phone', value: '' },
          { label: 'Location', value: '' },
          { label: 'LinkedIn', value: '' },
          { label: 'Portfolio', value: '' },
        ],
      },
      // Summary is off by default: it costs ~5 rendered lines (measured as the
      // difference between one page and two on a full resume) and most strong
      // one-page resumes lead straight into Skills. Still switchable per doc, and a
      // summary found in an imported CV is always kept.
      { id: 'summary', label: 'Summary', kind: 'text', on: false, text: '' },
      { id: 'skills', label: 'Skills', kind: 'chips', on: true, chips: [] },
      { id: 'experience', label: 'Experience', kind: 'blocks', on: true, blocks: [] },
      { id: 'education', label: 'Education', kind: 'blocks', on: true, blocks: [] },
      { id: 'projects', label: 'Projects', kind: 'blocks', on: true, blocks: [] },
    ],
  }
}
