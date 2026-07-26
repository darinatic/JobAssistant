// Add or remove a single skill in a resume's "## Skills" section, treating the
// section body as a flat comma-separated list (the tailor's output format).
// Pure and idempotent so chip toggles can derive their state from the markdown.

// Matches a heading line whose text contains "skill" (## Skills, ## Technical Skills).
const SKILLS_HEADING = /^#{1,6}\s+.*skills?.*$/im

function splitItems(line: string): string[] {
  return line.split(',').map((s) => s.trim()).filter(Boolean)
}

// Locate the first non-empty content line under the Skills heading.
// Returns { idx, lines } or null if there is no Skills section.
function findSkillsLine(md: string): { idx: number; lines: string[] } | null {
  const lines = md.split('\n')
  const headingIdx = lines.findIndex((l) => SKILLS_HEADING.test(l))
  if (headingIdx === -1) return null
  for (let i = headingIdx + 1; i < lines.length; i++) {
    if (/^#{1,6}\s/.test(lines[i])) break // next section, no content
    if (lines[i].trim()) return { idx: i, lines }
  }
  return null
}

export function skillInResume(md: string, skill: string): boolean {
  const found = findSkillsLine(md)
  if (!found) return false
  const target = skill.trim().toLowerCase()
  return splitItems(found.lines[found.idx]).some((s) => s.toLowerCase() === target)
}

export function patchSkillsLine(md: string, skill: string, op: 'add' | 'remove'): string {
  const clean = skill.trim()
  if (!clean) return md
  const found = findSkillsLine(md)

  if (!found) {
    if (op === 'remove') return md
    // No Skills section: append one at end of document.
    const sep = md.endsWith('\n') ? '' : '\n'
    return `${md}${sep}\n## Skills\n\n${clean}\n`
  }

  const { idx, lines } = found
  const items = splitItems(lines[idx])
  const lower = clean.toLowerCase()
  const has = items.some((s) => s.toLowerCase() === lower)

  if (op === 'add') {
    if (has) return md // idempotent
    items.push(clean)
  } else {
    if (!has) return md // idempotent
    const next = items.filter((s) => s.toLowerCase() !== lower)
    items.length = 0
    items.push(...next)
  }
  lines[idx] = items.join(', ')
  return lines.join('\n')
}
