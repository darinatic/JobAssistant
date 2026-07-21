import { describe, it, expect } from 'vitest'
import { Editor } from '@tiptap/core'
import { resumeEditorExtensions } from './resume-editor-extensions'

function roundTrip(md: string): string {
  const editor = new Editor({ extensions: resumeEditorExtensions, content: md })
  const out = editor.storage.markdown.getMarkdown()
  editor.destroy()
  return out
}

describe('resumeEditorExtensions markdown round-trip', () => {
  it('preserves headings, bullets, and bold', () => {
    const out = roundTrip('# Jane Tan\n\nAI Engineer · jane@x.com\n\n## Experience\n\n- Built **RAG** pipeline\n- Shipped TTS agent')
    expect(out).toContain('# Jane Tan')
    expect(out).toContain('## Experience')
    expect(out).toContain('- Built **RAG** pipeline')
    expect(out).toContain('- Shipped TTS agent')
  })

  it('uses - bullet markers (matches the LaTeX renderer + page estimator)', () => {
    const out = roundTrip('## Skills\n\n- PyTorch\n- Kubernetes')
    expect(out).not.toContain('* PyTorch')
    expect(out).toContain('- PyTorch')
  })

  it('preserves a markdown link through the round-trip', () => {
    const out = roundTrip('## Links\n\n- [GitHub](https://github.com/example)')
    expect(out).toContain('[GitHub](https://github.com/example)')
  })

  it('does not escape contact separators or spelled-out abbreviations', () => {
    // The LaTeX renderer splits the contact line on · and the tailor emits
    // "Machine Learning (ML)" style parens — neither must be backslash-escaped.
    const out = roundTrip('# Jane Tan\n\nAI Engineer · Singapore · Machine Learning (ML)')
    expect(out).toContain('AI Engineer · Singapore · Machine Learning (ML)')
    expect(out).not.toContain('\\·')
    expect(out).not.toContain('\\(')
  })
})
