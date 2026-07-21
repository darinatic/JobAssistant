import { useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { ResumeEditor } from './ResumeEditor'

// The resume editor + live preview, with an "Expand" button that opens the same
// editor in a near-full-screen dialog for real room to work. Both the inline and
// the expanded editor are controlled by the same value/onChange, so edits in either
// stay in lockstep — no separate syncing needed.
export function ResumeWorkspace({ value, onChange, showPageBadge = false, label = 'resume' }: {
  value: string
  onChange: (md: string) => void
  showPageBadge?: boolean
  label?: string
}) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div className="space-y-1.5">
      <div className="flex justify-end">
        <Button type="button" size="sm" variant="ghost" className="h-7 px-2 text-xs"
          onClick={() => setExpanded(true)}>⤢ Expand</Button>
      </div>
      <ResumeEditor value={value} onChange={onChange} showPageBadge={showPageBadge} />

      <Dialog open={expanded} onOpenChange={setExpanded}>
        <DialogContent className="flex h-[90vh] w-[95vw] max-w-6xl flex-col p-0">
          <DialogHeader className="border-b px-5 py-3">
            <DialogTitle className="eyebrow">edit {label}</DialogTitle>
          </DialogHeader>
          <div className="flex-1 overflow-auto p-5">
            <ResumeEditor value={value} onChange={onChange} showPageBadge={showPageBadge} />
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
