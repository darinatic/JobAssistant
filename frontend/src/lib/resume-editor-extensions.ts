import StarterKit from '@tiptap/starter-kit'
import { Markdown } from 'tiptap-markdown'
import type { Extensions } from '@tiptap/core'

// ATS-safe schema: only headings (1-3), bold, italic, bullet lists, paragraphs.
// Everything else in StarterKit is disabled so users can't introduce content
// the LaTeX template can't render cleanly.
export const resumeEditorExtensions: Extensions = [
  StarterKit.configure({
    heading: { levels: [1, 2, 3] },
    codeBlock: false,
    code: false,
    blockquote: false,
    horizontalRule: false,
    strike: false,
    orderedList: false,
    underline: false,
    link: { openOnClick: false },
  }),
  Markdown.configure({
    html: false,
    tightLists: true,
    bulletListMarker: '-',
    transformPastedText: true,
  }),
]
