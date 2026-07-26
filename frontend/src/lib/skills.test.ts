import { describe, expect, it } from 'vitest'
import { patchSkillsLine, skillInResume } from './skills'

const RESUME = `# Jane Doe

## Skills

Python, PyTorch, RAG

## Experience

### ML Engineer, Acme | 2023 - Present
- Built things
`

describe('skillInResume', () => {
  it('finds a present skill case-insensitively', () => {
    expect(skillInResume(RESUME, 'pytorch')).toBe(true)
    expect(skillInResume(RESUME, 'Python')).toBe(true)
  })
  it('is false for an absent skill', () => {
    expect(skillInResume(RESUME, 'Kubernetes')).toBe(false)
  })
  it('does not match a substring of another item', () => {
    // "Go" must not match inside "Python"/"Django"
    expect(skillInResume('## Skills\n\nPython, Django', 'Go')).toBe(false)
  })
})

describe('patchSkillsLine add', () => {
  it('appends a new skill to the Skills list', () => {
    const out = patchSkillsLine(RESUME, 'Kubernetes', 'add')
    expect(out).toContain('Python, PyTorch, RAG, Kubernetes')
    expect(skillInResume(out, 'Kubernetes')).toBe(true)
  })
  it('is a no-op when the skill is already present', () => {
    expect(patchSkillsLine(RESUME, 'PyTorch', 'add')).toBe(RESUME)
  })
  it('creates a Skills section when none exists', () => {
    const md = '# Jane Doe\n\n## Experience\n\n- did things\n'
    const out = patchSkillsLine(md, 'Go', 'add')
    expect(out).toContain('## Skills')
    expect(skillInResume(out, 'Go')).toBe(true)
  })
})

describe('patchSkillsLine remove', () => {
  it('removes a skill and repairs the comma list', () => {
    const out = patchSkillsLine(RESUME, 'PyTorch', 'remove')
    expect(out).toContain('Python, RAG')
    expect(skillInResume(out, 'PyTorch')).toBe(false)
  })
  it('removes the first item cleanly', () => {
    const out = patchSkillsLine(RESUME, 'Python', 'remove')
    expect(out).toContain('PyTorch, RAG')
    expect(out).not.toMatch(/,\s*PyTorch/)
  })
  it('is a no-op when the skill is absent', () => {
    expect(patchSkillsLine(RESUME, 'Kubernetes', 'remove')).toBe(RESUME)
  })
})
