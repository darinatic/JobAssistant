// tiptap-markdown@0.9's shipped .d.ts declares `MarkdownStorage` but doesn't
// perform the module augmentation that wires it onto TipTap's `Storage`
// interface (the pattern every other TipTap extension's typings use). Without
// this, `editor.storage.markdown` doesn't type-check even though it exists at
// runtime (proven by the round-trip test).
import type { MarkdownStorage } from 'tiptap-markdown'

declare module '@tiptap/core' {
  interface Storage {
    markdown: MarkdownStorage
  }
}
