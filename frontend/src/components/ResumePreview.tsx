import type { ReactNode } from 'react'
import { parseResume } from '@/lib/resume-preview'

// Minimal inline formatter: **bold**, *italic*, [text](url). Non-nested — good
// enough for an approximate resume preview.
function inline(text: string, keyBase: string): ReactNode[] {
  const nodes: ReactNode[] = []
  const re = /\*\*(.+?)\*\*|\*(.+?)\*|\[(.+?)\]\((.+?)\)/g
  let last = 0
  let k = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index))
    if (m[1] != null) nodes.push(<strong key={`${keyBase}-${k++}`}>{m[1]}</strong>)
    else if (m[2] != null) nodes.push(<em key={`${keyBase}-${k++}`}>{m[2]}</em>)
    else if (m[3] != null) {
      const href = m[4].trim()
      // Allow only safe schemes — resume text flows through the LLM tailor
      // (fed attacker-controllable JD text), so block javascript:/data: etc.
      const safe = /^(https?:|mailto:|tel:|#|\/)/i.test(href) ? href : '#'
      nodes.push(<a key={`${keyBase}-${k++}`} href={safe} target="_blank" rel="noreferrer">{m[3]}</a>)
    }
    last = re.lastIndex
  }
  if (last < text.length) nodes.push(text.slice(last))
  return nodes
}

// Client-side approximation of the ATS single-column LaTeX template. Not
// pixel-identical to the PDF — the "Download resume PDF" button is exact truth.
export function ResumePreview({ md }: { md: string }) {
  const blocks = parseResume(md)
  return (
    <div className="resume-preview overflow-auto rounded-md bg-white p-6 font-sans text-[11px] leading-snug text-black shadow-inner">
      {blocks.map((b, i) => {
        switch (b.kind) {
          case 'name':
            return <h1 key={i} className="text-center text-lg font-bold tracking-tight">{inline(b.text, `n${i}`)}</h1>
          case 'contact':
            return (
              <p key={i} className="mb-2 text-center text-[10px]">
                {b.items.map((it, j) => (
                  <span key={j}>{j > 0 ? '  ·  ' : ''}{inline(it, `c${i}-${j}`)}</span>
                ))}
              </p>
            )
          case 'section':
            return <h2 key={i} className="mt-3 mb-1 border-b border-black/60 pb-0.5 text-[12px] font-bold uppercase tracking-wide">{inline(b.text, `s${i}`)}</h2>
          case 'role':
            return <p key={i} className="mt-1.5 font-semibold">{inline(b.text, `r${i}`)}</p>
          case 'bullets':
            return (
              <ul key={i} className="my-0.5 list-disc pl-5">
                {b.items.map((it, j) => <li key={j}>{inline(it, `b${i}-${j}`)}</li>)}
              </ul>
            )
          case 'para':
            return <p key={i} className="my-0.5">{inline(b.text, `p${i}`)}</p>
        }
      })}
    </div>
  )
}
