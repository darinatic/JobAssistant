export type ResumeBlock =
  | { kind: 'name'; text: string }
  | { kind: 'contact'; items: string[] }
  | { kind: 'section'; text: string }
  | { kind: 'role'; text: string; date?: string }
  | { kind: 'bullets'; items: string[] }
  | { kind: 'para'; text: string }

// Split a contact line on the usual separators (· • | or 2+ spaces).
const CONTACT_SEP = /\s*[·•|]\s*|\s{2,}/

// Block-level parser mirroring src/utils/latex_renderer.py markdown_to_latex,
// including the "first paragraph after the name is the contact line even across
// one blank line" rule (kept in sync with the Task 1 backend tweak).
export function parseResume(md: string): ResumeBlock[] {
  const lines = (md ?? '').replace(/\r\n/g, '\n').split('\n')
  const blocks: ResumeBlock[] = []
  let i = 0
  while (i < lines.length && !lines[i].trim()) i++

  if (i < lines.length && lines[i].startsWith('# ')) {
    blocks.push({ kind: 'name', text: lines[i].slice(2).trim() })
    i++
    if (
      i + 1 < lines.length && !lines[i].trim() &&
      lines[i + 1].trim() && !lines[i + 1].startsWith('#')
    ) {
      i++
    }
    const contact: string[] = []
    while (i < lines.length && lines[i].trim() && !lines[i].startsWith('#')) {
      contact.push(lines[i].trim())
      i++
    }
    if (contact.length) {
      const items = contact.join(' · ').split(CONTACT_SEP).map((s) => s.trim()).filter(Boolean)
      blocks.push({ kind: 'contact', items })
    }
  }

  let bullets: string[] | null = null
  const flush = () => {
    if (bullets) { blocks.push({ kind: 'bullets', items: bullets }); bullets = null }
  }
  for (; i < lines.length; i++) {
    const s = lines[i].trim()
    if (!s) { flush(); continue }
    if (s.startsWith('## ')) { flush(); blocks.push({ kind: 'section', text: s.slice(3).trim() }) }
    else if (s.startsWith('### ')) {
      flush()
      const heading = s.slice(4).trim()
      // Mirror the backend's rpartition(" | "): split on the LAST " | " so a
      // trailing date renders right-aligned, matching the PDF layout.
      const idx = heading.lastIndexOf(' | ')
      if (idx === -1) blocks.push({ kind: 'role', text: heading })
      else blocks.push({ kind: 'role', text: heading.slice(0, idx).trim(), date: heading.slice(idx + 3).trim() })
    }
    else if (s.startsWith('#')) { flush(); blocks.push({ kind: 'role', text: s.replace(/^#+\s*/, '').trim() }) }
    else if (/^[-*+]\s+/.test(s)) { (bullets ??= []).push(s.replace(/^[-*+]\s+/, '').trim()) }
    else { flush(); blocks.push({ kind: 'para', text: s }) }
  }
  flush()
  return blocks
}
