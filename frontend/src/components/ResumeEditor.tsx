import { useEffect } from 'react'
import { useEditor, EditorContent, type Editor } from '@tiptap/react'
import { resumeEditorExtensions } from '@/lib/resume-editor-extensions'
import { ResumePreview } from './ResumePreview'
import { estimatePageFit } from '@/lib/page-fit'
import { Button } from '@/components/ui/button'

function PageFit({ md }: { md: string }) {
  const f = estimatePageFit(md)
  return f.fits
    ? <span className="font-mono text-xs" style={{ color: 'var(--have)' }}>≈ 1 page ✓</span>
    : <span className="font-mono text-xs" style={{ color: 'var(--gap)' }}>≈ {f.pages} pages · trim ~{f.overflow} lines</span>
}

function Toolbar({ editor }: { editor: Editor | null }) {
  if (!editor) return null
  const btn = (active: boolean, on: () => void, label: string) => (
    <Button type="button" size="sm" variant={active ? 'default' : 'ghost'}
      className="h-7 px-2 text-xs" onMouseDown={(e) => e.preventDefault()} onClick={on}>{label}</Button>
  )
  return (
    <div className="flex flex-wrap items-center gap-1 border-b p-1.5">
      {btn(editor.isActive('heading', { level: 1 }), () => editor.chain().focus().toggleHeading({ level: 1 }).run(), 'Name')}
      {btn(editor.isActive('heading', { level: 2 }), () => editor.chain().focus().toggleHeading({ level: 2 }).run(), 'Section')}
      {btn(editor.isActive('heading', { level: 3 }), () => editor.chain().focus().toggleHeading({ level: 3 }).run(), 'Role')}
      {btn(editor.isActive('bold'), () => editor.chain().focus().toggleBold().run(), 'B')}
      {btn(editor.isActive('italic'), () => editor.chain().focus().toggleItalic().run(), 'I')}
      {btn(editor.isActive('bulletList'), () => editor.chain().focus().toggleBulletList().run(), '• List')}
    </div>
  )
}

export function ResumeEditor({ value, onChange, showPageBadge = false }: {
  value: string
  onChange: (md: string) => void
  showPageBadge?: boolean
}) {
  const editor = useEditor({
    extensions: resumeEditorExtensions,
    content: value,
    onUpdate: ({ editor }) => onChange(editor.storage.markdown.getMarkdown()),
    editorProps: {
      attributes: {
        class: 'prose prose-sm max-w-none min-h-[18rem] p-3 focus:outline-none font-mono text-xs',
      },
    },
  })

  // Controlled: push external value changes into the editor, but never while the
  // markdown already matches (that would clobber the caret mid-type).
  useEffect(() => {
    if (!editor) return
    if (value !== editor.storage.markdown.getMarkdown()) {
      // TipTap v3 signature. For the v2 fallback use: setContent(value, false)
      editor.commands.setContent(value, { emitUpdate: false })
    }
  }, [value, editor])

  return (
    <div className="grid gap-3 md:grid-cols-2">
      <div className="rounded-lg border bg-background">
        <Toolbar editor={editor} />
        <EditorContent editor={editor} />
      </div>
      <div className="rounded-lg border bg-muted/30 p-2">
        <div className="mb-1 flex items-center justify-between px-1">
          <span className="eyebrow">preview</span>
          {showPageBadge && <PageFit md={value} />}
        </div>
        <ResumePreview md={value} />
        <p className="px-1 pt-1 text-[10px] text-muted-foreground">Approximate, download the PDF for the exact layout.</p>
      </div>
    </div>
  )
}
