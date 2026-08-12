import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import { api } from '@/lib/api'
import { estimatePageFit } from '@/lib/page-fit'
import {
  type Block,
  type ResumeDoc,
  type Section,
  blankDoc,
  fromMonthInput,
  hasContent,
  serialize,
  toMonthInput,
  unreviewedCount,
} from '@/lib/resume-doc'
import {
  addBlock, addBullet, addChip, moveBlock, moveSection, removeBlock, removeBullet,
  removeChip, resolveIssue, setBlockField, setBullet, setField, setLabel, setText,
  toggleBlockCurrent, toggleBlockOn, toggleBulletOn, toggleChip, toggleSectionOn,
} from '@/lib/resume-doc-ops'

const mono = { fontFamily: 'var(--font-mono)' } as const
const micro: React.CSSProperties = { ...mono, fontSize: 9, letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--dim)' }
const inputStyle: React.CSSProperties = { width: '100%', boxSizing: 'border-box', border: '2px solid var(--ink)', background: 'var(--paper)', padding: '10px 12px', fontSize: 14, fontFamily: 'inherit', color: 'inherit' }

function sectionCount(s: Section): number {
  if (s.kind === 'fields') return (s.fields ?? []).filter((f) => f.value.trim()).length
  if (s.kind === 'chips') return (s.chips ?? []).filter((c) => c.on).length
  if (s.kind === 'blocks') return (s.blocks ?? []).filter((b) => b.on).length
  return (s.text ?? '').trim() ? 1 : 0
}

// ---- nav rail --------------------------------------------------------------

function NavRail({ doc, activeId, onPick, set }: {
  doc: ResumeDoc; activeId: string; onPick: (id: string) => void; set: (d: ResumeDoc) => void
}) {
  const [drag, setDrag] = useState<number | null>(null)
  const [over, setOver] = useState<number | null>(null)
  const shown = doc.sections.filter((s) => s.on || s.id === 'contact').length
  const toReview = unreviewedCount(doc)
  return (
    <div style={{ borderRight: '2px solid var(--ink)', display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '11px 16px', borderBottom: '1px solid var(--rule)', display: 'flex', justifyContent: 'space-between' }}>
        <span style={micro}>sections · drag to reorder</span>
        <span style={micro}>{shown}/{doc.sections.length} on</span>
      </div>
      <div style={{ padding: '8px 16px', borderBottom: '1px solid var(--rule)', display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ width: 8, height: 8, flex: '0 0 8px', background: toReview ? 'var(--honesty)' : 'var(--have)' }} />
        <span style={{ ...micro, fontSize: 9 }}>{toReview ? `${toReview} section${toReview > 1 ? 's' : ''} to review` : 'all sections confirmed'}</span>
      </div>
      {doc.sections.map((s, i) => {
        const active = s.id === activeId
        const locked = s.id === 'contact'
        const isOver = over === i && drag !== i
        return (
          <div
            key={s.id}
            draggable={!locked && drag === i}
            onDragOver={(e) => { e.preventDefault(); if (over !== i) setOver(i) }}
            onDrop={(e) => { e.preventDefault(); if (drag !== null && drag !== i) set(moveSection(doc, drag, i)); setDrag(null); setOver(null) }}
            onDragEnd={() => { setDrag(null); setOver(null) }}
            style={{
              display: 'flex', alignItems: 'center', gap: 8, padding: '0 12px',
              borderBottom: '1px solid var(--rule)',
              background: active ? 'var(--ink)' : 'transparent', color: active ? 'var(--paper)' : 'var(--ink)',
              opacity: drag === i ? 0.4 : 1, boxShadow: isOver ? 'inset 0 3px 0 0 var(--have)' : undefined,
            }}
          >
            <span
              onMouseDown={() => !locked && setDrag(i)}
              title={locked ? 'contact stays first' : 'drag to reorder'}
              style={{ ...mono, fontSize: 13, cursor: locked ? 'default' : 'grab', color: active ? 'var(--paper)' : 'var(--dim)', opacity: locked ? 0.3 : 1, userSelect: 'none' }}
            >⠿</span>
            <button
              onClick={() => !locked && set(toggleSectionOn(doc, s.id))}
              title={locked ? 'contact is always on' : 'show in resume'}
              style={{ width: 16, height: 16, flex: '0 0 16px', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: locked ? 'not-allowed' : 'pointer', border: `2px solid ${(s.on || locked) ? (active ? 'var(--paper)' : 'var(--ink)') : 'var(--hair)'}`, background: (s.on || locked) ? (active ? 'var(--paper)' : 'var(--ink)') : 'transparent', color: active ? 'var(--ink)' : 'var(--paper)', ...mono, fontSize: 9, opacity: locked ? 0.5 : 1 }}
            >{(s.on || locked) ? '✓' : ''}</button>
            <button onClick={() => onPick(s.id)} style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 8, padding: '12px 0', border: 0, background: 'transparent', color: 'inherit', cursor: 'pointer', textAlign: 'left', font: 'inherit', opacity: (s.on || locked) ? 1 : 0.45 }}>
              <span style={{ ...mono, fontSize: 10, color: active ? 'var(--paper)' : 'var(--dim)' }}>{String(i + 1).padStart(2, '0')}</span>
              <span style={{ flex: 1, fontWeight: 600, fontSize: 14 }}>{s.label}</span>
              <span style={{ ...mono, fontSize: 11, fontWeight: 700, color: active ? 'var(--paper)' : 'var(--dim)' }}>{sectionCount(s)}</span>
              <span title={s.issue && !s.reviewed ? 'needs a look' : undefined} style={{ width: 7, height: 7, flex: '0 0 7px', background: s.issue && !s.reviewed ? 'var(--honesty)' : 'transparent' }} />
            </button>
          </div>
        )
      })}
    </div>
  )
}

// ---- block editor (experience/education/certs/awards/projects) -------------

function BlockCard({ sec, block, index, set, drag, setDrag, over, setOver }: {
  sec: Section; block: Block; index: number; set: (d: ResumeDoc) => void
  drag: number | null; setDrag: (n: number | null) => void; over: number | null; setOver: (n: number | null) => void
}) {
  const on = block.on
  const isOver = over === index && drag !== index
  const isCert = sec.id === 'certifications'
  return (
    <div
      draggable={drag === index}
      onDragOver={(e) => { e.preventDefault(); if (over !== index) setOver(index) }}
      onDrop={(e) => { e.preventDefault(); if (drag !== null && drag !== index) set(moveBlock(dref.current, sec.id, drag, index)) }}
      onDragEnd={() => { setDrag(null); setOver(null) }}
      style={{ border: `2px solid ${isOver ? 'var(--have)' : 'var(--ink)'}`, background: 'var(--paper)', opacity: drag === index ? 0.45 : 1 }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 14px', borderBottom: '1px solid var(--rule)', background: 'var(--surface)' }}>
        <span onMouseDown={() => setDrag(index)} title="drag to reorder" style={{ ...mono, fontSize: 14, cursor: 'grab', color: 'var(--dim)', userSelect: 'none' }}>⠿</span>
        <button onClick={() => set(toggleBlockOn(dref.current, sec.id, block.id))} title="show in resume" style={{ width: 16, height: 16, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', border: `2px solid ${on ? 'var(--ink)' : 'var(--hair)'}`, background: on ? 'var(--ink)' : 'transparent', color: 'var(--paper)', ...mono, fontSize: 9 }}>{on ? '✓' : ''}</button>
        <span style={{ ...mono, fontSize: 11, fontWeight: 700, color: 'var(--dim)' }}>{String(index + 1).padStart(2, '0')}</span>
        {!on && <span style={{ ...micro, fontSize: 9, border: '1px solid var(--hair)', padding: '2px 6px' }}>not on resume</span>}
        <span style={{ flex: 1 }} />
        <button onClick={() => set(removeBlock(dref.current, sec.id, block.id))} style={{ border: '1px solid var(--honesty)', background: 'transparent', color: 'var(--honesty)', padding: '3px 8px', cursor: 'pointer', ...mono, fontSize: 9, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase' }}>delete</button>
      </div>
      <div style={{ opacity: on ? 1 : 0.45 }}>
        <div style={{ padding: '12px 14px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <Field label={sec.id === 'education' ? 'Degree' : isCert ? 'Certification' : 'Title'} value={block.title} onChange={(v) => set(setBlockField(dref.current, sec.id, block.id, 'title', v))} big />
          <Field label={orgLabel(sec)} value={block.org} onChange={(v) => set(setBlockField(dref.current, sec.id, block.id, 'org', v))} />
          {isCert && <Field label="Credential ID" value={block.credential ?? ''} onChange={(v) => set(setBlockField(dref.current, sec.id, block.id, 'credential', v))} mono />}
          <div style={{ gridColumn: '1 / -1', display: 'flex', gap: 18, alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <MonthField label="Start" value={block.startDate} onChange={(v) => set(setBlockField(dref.current, sec.id, block.id, 'startDate', v))} />
            {block.current ? (
              <div>
                <p style={{ ...micro, margin: '0 0 5px' }}>End</p>
                <span style={{ ...mono, fontSize: 13, fontWeight: 700, borderBottom: '2px solid var(--ink)', padding: '6px 0', display: 'inline-block', width: 150 }}>Present</span>
              </div>
            ) : (
              <MonthField label="End" value={block.endDate} onChange={(v) => set(setBlockField(dref.current, sec.id, block.id, 'endDate', v))} />
            )}
            <label style={{ display: 'flex', alignItems: 'center', gap: 7, cursor: 'pointer', paddingBottom: 6 }}>
              <input type="checkbox" checked={block.current} onChange={() => set(toggleBlockCurrent(dref.current, sec.id, block.id))} style={{ width: 15, height: 15, accentColor: 'var(--ink)', cursor: 'pointer' }} />
              <span style={{ ...micro, fontSize: 10 }}>currently here</span>
            </label>
          </div>
        </div>
        {!isCert && (
          <div style={{ padding: '0 14px 14px', display: 'flex', flexDirection: 'column', gap: 8 }}>
            {block.bullets.map((l) => (
              <div key={l.id} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                <button onClick={() => set(toggleBulletOn(dref.current, sec.id, block.id, l.id))} title="show this bullet" style={{ marginTop: 6, width: 14, height: 14, flex: '0 0 14px', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', border: `2px solid ${l.on ? 'var(--ink)' : 'var(--hair)'}`, background: l.on ? 'var(--ink)' : 'transparent', color: 'var(--paper)', ...mono, fontSize: 8 }}>{l.on ? '✓' : ''}</button>
                <textarea value={l.text} onChange={(e) => set(setBullet(dref.current, sec.id, block.id, l.id, e.target.value))} placeholder="what you did, and what changed because of it" rows={1}
                  style={{ flex: 1, boxSizing: 'border-box', border: 0, borderBottom: '1.5px solid var(--rule)', background: 'transparent', padding: '5px 0', fontSize: 14, lineHeight: 1.5, resize: 'vertical', color: 'inherit', fontFamily: 'inherit', textDecoration: l.on ? 'none' : 'line-through', opacity: l.on ? 1 : 0.5 }} />
                <button onClick={() => set(removeBullet(dref.current, sec.id, block.id, l.id))} style={{ border: 0, background: 'transparent', cursor: 'pointer', ...mono, fontSize: 13, color: 'var(--dim)', padding: '6px 4px' }}>×</button>
              </div>
            ))}
            <button onClick={() => set(addBullet(dref.current, sec.id, block.id))} style={{ alignSelf: 'flex-start', border: 0, background: 'transparent', cursor: 'pointer', ...mono, fontSize: 10, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--dim)', padding: '4px 0' }}>+ bullet</button>
          </div>
        )}
      </div>
    </div>
  )
}

// dref: a ref to the *current* doc so block-card callbacks always mutate the
// latest state (the cards are mapped from a snapshot; without this, two edits in
// one render batch would clobber each other).
const dref = { current: { version: 1, sections: [] } as ResumeDoc }

const ORG_LABELS: Record<string, string> = {
  education: 'Institution', certifications: 'Issuer', awards: 'Awarding body', projects: 'Context',
}
const orgLabel = (sec: Section) => ORG_LABELS[sec.id] ?? 'Company'

// A month input (native <input type="month">) that stores MM/YYYY; falls back to a
// plain MM/YYYY text field for values that aren't a clean month (year-only, etc.).
function MonthField({ label, value, onChange, disabled }: {
  label: string; value: string; onChange: (v: string) => void; disabled?: boolean
}) {
  const monthVal = toMonthInput(value)
  const native = !value || !!monthVal
  const st: React.CSSProperties = {
    border: 0, borderBottom: `2px solid ${value ? 'var(--ink)' : 'var(--hair)'}`, background: 'transparent',
    padding: '6px 0', fontFamily: 'var(--font-mono)', fontSize: 13, color: 'inherit', width: 150, opacity: disabled ? 0.4 : 1,
  }
  return (
    <div>
      <p style={{ ...micro, margin: '0 0 5px' }}>{label}</p>
      {native ? (
        <input type="month" value={monthVal} disabled={disabled} onChange={(e) => onChange(fromMonthInput(e.target.value))} style={st} />
      ) : (
        <input type="text" value={value} disabled={disabled} placeholder="MM/YYYY" onChange={(e) => onChange(e.target.value)} style={st} />
      )}
    </div>
  )
}

function Field({ label, value, onChange, big, mono: isMono }: {
  label: string; value: string; onChange: (v: string) => void; big?: boolean; mono?: boolean
}) {
  return (
    <div>
      <p style={{ ...micro, margin: '0 0 5px' }}>{label}</p>
      <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={label}
        style={{ ...inputStyle, border: 0, borderBottom: `2px solid ${value ? 'var(--ink)' : 'var(--hair)'}`, padding: '6px 0', fontSize: big ? 17 : 14, fontWeight: big ? 600 : 400, fontFamily: isMono ? 'var(--font-mono)' : 'inherit' }} />
    </div>
  )
}

// ---- section editor --------------------------------------------------------

function SectionEditor({ sec, set }: { sec: Section; set: (d: ResumeDoc) => void }) {
  const [chipDraft, setChipDraft] = useState('')
  const [drag, setDrag] = useState<number | null>(null)
  const [over, setOver] = useState<number | null>(null)

  if (sec.kind === 'fields') {
    return (
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {(sec.fields ?? []).map((f, i) => (
          <div key={f.label}>
            <p style={{ ...micro, margin: '0 0 6px' }}>{f.label}</p>
            <input value={f.value} onChange={(e) => set(setField(dref.current, sec.id, i, e.target.value))} placeholder="not found in the document"
              style={{ ...inputStyle, border: `2px solid ${f.value ? 'var(--ink)' : 'var(--hair)'}` }} />
          </div>
        ))}
      </div>
    )
  }

  if (sec.kind === 'text') {
    const words = (sec.text ?? '').split(/\s+/).filter(Boolean).length
    const isSummary = sec.id === 'summary'
    return (
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
          <p style={{ ...micro, margin: 0 }}>{sec.label} paragraph</p>
          <p style={{ ...micro, margin: 0, letterSpacing: '0.08em' }}>
            {words} words · aim {isSummary ? '25–45' : '40–60'}
          </p>
        </div>
        <textarea value={sec.text ?? ''} onChange={(e) => set(setText(dref.current, sec.id, e.target.value))}
          style={{ ...inputStyle, minHeight: 150, lineHeight: 1.6, resize: 'vertical' }} />
        {isSummary && (
          <p style={{ fontSize: 13, color: 'var(--dim)', marginTop: 9, lineHeight: 1.5 }}>
            Optional, and off by default. A summary costs about 5 lines, which is often
            the difference between one page and two. Most strong one page resumes skip
            it and lead with Skills. Switch it on in the rail if you want one.
          </p>
        )}
        <p style={{ fontSize: 13, color: 'var(--dim)', marginTop: 9, lineHeight: 1.5 }}>Kept verbatim from your resume. The tailor step rewrites this per job, and only when the section is on. The builder never edits your words.</p>
      </div>
    )
  }

  if (sec.kind === 'chips') {
    const chips = sec.chips ?? []
    const add = () => { const v = chipDraft.trim(); if (v) { set(addChip(dref.current, sec.id, v)); setChipDraft('') } }
    return (
      <div>
        <p style={{ ...micro, margin: '0 0 10px' }}>{chips.filter((c) => c.on).length} skills on · click to switch off</p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {chips.map((c) => (
            <span key={c.text} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, border: `2px solid ${c.on ? 'var(--ink)' : 'var(--hair)'}`, background: c.on ? 'var(--have-bg, transparent)' : 'transparent' }}>
              <button onClick={() => set(toggleChip(dref.current, sec.id, c.text))} style={{ ...mono, fontSize: 12, fontWeight: 500, padding: '7px 10px', cursor: 'pointer', border: 0, background: 'transparent', color: c.on ? 'var(--ink)' : 'var(--dim)', textDecoration: c.on ? 'none' : 'line-through' }}>{c.text}</button>
              <button onClick={() => set(removeChip(dref.current, sec.id, c.text))} title="remove" style={{ border: 0, background: 'transparent', cursor: 'pointer', ...mono, fontSize: 12, color: 'var(--dim)', padding: '0 8px 0 0' }}>×</button>
            </span>
          ))}
        </div>
        <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
          <input value={chipDraft} onChange={(e) => setChipDraft(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add() } }} placeholder="add a skill, press enter" style={{ ...inputStyle, flex: 1 }} />
          <button onClick={add} className="ov-btn ov-btn-ink">add</button>
        </div>
      </div>
    )
  }

  // blocks
  const blocks = sec.blocks ?? []
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {blocks.map((b, i) => (
        <BlockCard key={b.id} sec={sec} block={b} index={i} set={set} drag={drag} setDrag={setDrag} over={over} setOver={setOver} />
      ))}
      <button onClick={() => set(addBlock(dref.current, sec.id))} style={{ border: '2px dashed var(--hair)', background: 'transparent', padding: 15, cursor: 'pointer', ...mono, fontSize: 11, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--dim)' }}>
        + add {sec.id === 'education' ? 'degree' : sec.id === 'certifications' ? 'certification' : sec.id === 'awards' ? 'award' : sec.id === 'projects' ? 'project' : 'role'}
      </button>
    </div>
  )
}

// ---- preview (real Tectonic PDF) -------------------------------------------

const TEMPLATES: Array<'standard' | 'compact'> = ['standard', 'compact']

function PreviewPane({ doc, onTailor }: { doc: ResumeDoc; onTailor: () => void }) {
  const md = useMemo(() => serialize(doc, { include: 'enabled' }), [doc])
  const [tpl, setTpl] = useState<'standard' | 'compact'>('standard')
  const [renderedMd, setRenderedMd] = useState<string | null>(null)
  const [renderedTpl, setRenderedTpl] = useState<'standard' | 'compact'>('standard')
  const [url, setUrl] = useState<string | null>(null)
  const [rendering, setRendering] = useState(false)
  const dirty = md !== renderedMd || tpl !== renderedTpl
  // Templates render at different densities, so the page badge has to be estimated
  // against the one that is actually selected.
  const fit = estimatePageFit(md, tpl)

  async function render() {
    if (rendering) return
    setRendering(true)
    try {
      const blob = await api.resumePdf(md, tpl)
      const next = URL.createObjectURL(blob)
      setUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return next })
      setRenderedMd(md)
      setRenderedTpl(tpl)
    } catch {
      toast.error('Could not render the PDF. Is the backend running?')
    } finally {
      setRendering(false)
    }
  }

  async function downloadPdf() {
    try {
      const blob = await api.resumePdf(md, tpl)
      const a = document.createElement('a')
      const href = URL.createObjectURL(blob)
      a.href = href; a.download = 'resume.pdf'; a.click(); URL.revokeObjectURL(href)
    } catch { toast.error('Download failed.') }
  }

  return (
    <div style={{ borderLeft: '2px solid var(--ink)', background: 'var(--surface)', display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '13px 18px', borderBottom: '2px solid var(--ink)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'var(--paper)' }}>
        <span style={micro}>render · ≈ {fit.pages} page{fit.pages > 1 ? 's' : ''}{fit.fits ? ' ✓' : ''}</span>
        <div style={{ display: 'flex', border: '1.5px solid var(--ink)' }}>
          {TEMPLATES.map((t) => (
            <button key={t} onClick={() => setTpl(t)}
              style={{ ...mono, fontSize: 10, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', padding: '6px 11px', cursor: 'pointer', border: 0, borderLeft: t === 'compact' ? '1.5px solid var(--ink)' : undefined, background: tpl === t ? 'var(--ink)' : 'transparent', color: tpl === t ? 'var(--paper)' : 'var(--dim)' }}>
              {t}
            </button>
          ))}
        </div>
      </div>
      <div style={{ padding: '11px 18px', borderBottom: '2px solid var(--ink)', display: 'flex', alignItems: 'center', gap: 12, background: dirty || rendering ? 'var(--honesty-bg, transparent)' : 'transparent' }}>
        <span style={{ width: 8, height: 8, flex: '0 0 8px', background: dirty || rendering ? 'var(--honesty)' : 'var(--have)' }} />
        <span style={{ ...micro, flex: 1, letterSpacing: '0.08em', color: 'var(--ink)' }}>{rendering ? 'laying out page…' : dirty ? 'edits not in this render' : 'render matches your draft'}</span>
        <button onClick={render} disabled={!dirty || rendering} className="ov-btn" style={{ opacity: !dirty && !rendering ? 0.5 : 1 }}>{rendering ? 'rendering…' : dirty ? 'render' : 'up to date'}</button>
      </div>
      <div style={{ flex: 1, minHeight: 420, background: 'var(--rule)' }}>
        {url ? (
          <iframe title="resume preview" src={url} style={{ width: '100%', height: '100%', minHeight: 420, border: 0, background: 'white' }} />
        ) : (
          <div style={{ height: '100%', minHeight: 420, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, textAlign: 'center' }}>
            <span style={{ ...micro, lineHeight: 2 }}>press render to see<br />your exact pdf</span>
          </div>
        )}
      </div>
      <div style={{ padding: '14px 18px', borderTop: '2px solid var(--ink)', background: 'var(--paper)', display: 'flex', gap: 10 }}>
        <button onClick={downloadPdf} disabled={dirty} className="ov-btn ov-btn-ink" style={{ flex: 1, justifyContent: 'center', opacity: dirty ? 0.55 : 1 }}>{dirty ? 'render first' : 'download pdf'}</button>
        <button onClick={onTailor} className="ov-btn">tailor →</button>
      </div>
    </div>
  )
}

// ---- post-parse reveal -----------------------------------------------------
// One structuring call already returned; we step through the REAL sections and
// their REAL confidence/flags so the moment is honest (only the reveal is paced).

function ParseReveal({ doc, onDone }: { doc: ResumeDoc; onDone: () => void }) {
  const [n, setN] = useState(0)
  const total = doc.sections.length
  useEffect(() => {
    if (n >= total) { const t = setTimeout(onDone, 550); return () => clearTimeout(t) }
    const t = setTimeout(() => setN((x) => x + 1), 320)
    return () => clearTimeout(t)
  }, [n, total, onDone])
  const pct = total ? Math.round((Math.min(n, total) / total) * 100) : 100
  return (
    <div className="ov-pad" style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', minHeight: 480 }}>
      <p style={micro}>builder · mapping sections</p>
      <h2 className="ov-h1" style={{ marginTop: 12 }}>Splitting your resume into sections<span style={{ animation: 'ov-blink 1s steps(1,end) infinite' }}>_</span></h2>
      <div style={{ marginTop: 24, display: 'flex', alignItems: 'center', gap: 16 }}>
        <div style={{ flex: 1, height: 14, border: '2px solid var(--ink)', overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${pct}%`, background: 'var(--ink)', transition: 'width .3s' }} />
        </div>
        <span style={{ ...mono, fontSize: 20, fontWeight: 700, minWidth: 56, textAlign: 'right' }}>{pct}%</span>
      </div>
      <div style={{ marginTop: 24, border: '2px solid var(--ink)' }}>
        {doc.sections.map((s, i) => {
          const done = i < n, now = i === n, flag = !!s.issue
          return (
            <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '11px 16px', borderBottom: i < total - 1 ? '1px solid var(--rule)' : undefined, opacity: done || now ? 1 : 0.35 }}>
              <span style={{ width: 8, height: 8, flex: '0 0 8px', background: done ? (flag ? 'var(--honesty)' : 'var(--have)') : now ? 'var(--honesty)' : 'var(--hair)', animation: now ? 'ov-blink .5s steps(1,end) infinite' : undefined }} />
              <span style={{ ...micro, width: 24 }}>{String(i + 1).padStart(2, '0')}</span>
              <span style={{ ...mono, fontSize: 13, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', width: 150 }}>{s.label}</span>
              <span style={{ flex: 1, ...mono, fontSize: 12, color: 'var(--dim)' }}>{done ? (flag ? 'needs a look' : 'mapped') : now ? 'reading…' : ''}</span>
              <span style={{ ...mono, fontSize: 12, fontWeight: 700, color: 'var(--dim)' }}>{done ? `${Math.round((s.conf ?? 1) * 100)}%` : ''}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ---- stage shell -----------------------------------------------------------

export function StageBuilder({ doc, setDoc, uploading, onUpload, onTailor }: {
  doc: ResumeDoc
  setDoc: (d: ResumeDoc) => void
  uploading: boolean
  onUpload: (f: File) => Promise<boolean>
  onTailor: () => void
}) {
  const [phase, setPhase] = useState<'import' | 'parsing' | 'reveal' | 'builder'>(() => (hasContent(doc) ? 'builder' : 'import'))
  const [activeId, setActiveId] = useState<string>(() => doc.sections[0]?.id ?? 'contact')
  const fileRef = useRef<HTMLInputElement>(null)
  dref.current = doc

  const set = (d: ResumeDoc) => { dref.current = d; setDoc(d) }

  async function importFile(file: File) {
    setPhase('parsing')
    const ok = await onUpload(file)
    setPhase(ok ? 'reveal' : 'import')
  }

  if (phase === 'reveal') {
    return <ParseReveal doc={doc} onDone={() => { setActiveId(doc.sections[0]?.id ?? 'contact'); setPhase('builder') }} />
  }

  if (phase === 'import') {
    return (
      <div className="ov-pad" style={{ flex: 1, display: 'flex', justifyContent: 'center' }}>
        <div style={{ width: 620, maxWidth: '100%', display: 'flex', flexDirection: 'column', gap: 16 }}>
          <p style={micro}>builder · input</p>
          <label style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 11, border: '2px dashed var(--ink)', padding: '48px 24px', cursor: 'pointer' }}>
            <span style={{ ...mono, fontSize: 30, fontWeight: 700 }}>[ + ]</span>
            <span style={{ ...mono, fontSize: 12, fontWeight: 700, letterSpacing: '0.16em', textTransform: 'uppercase' }}>{uploading ? 'parsing…' : 'drop resume or browse'}</span>
            <span style={{ fontSize: 14, color: 'var(--dim)' }}>PDF or DOCX · scans are read too</span>
            <input ref={fileRef} type="file" accept="application/pdf,.docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" style={{ display: 'none' }} onChange={(e) => e.target.files?.[0] && importFile(e.target.files[0])} />
          </label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ flex: 1, height: 2, background: 'var(--rule)' }} />
            <span style={{ ...micro, fontSize: 10 }}>or</span>
            <div style={{ flex: 1, height: 2, background: 'var(--rule)' }} />
          </div>
          <button onClick={() => { set(blankDoc()); setActiveId('contact'); setPhase('builder') }} className="ov-btn" style={{ justifyContent: 'center', padding: '14px' }}>start from a blank template</button>
        </div>
      </div>
    )
  }

  if (phase === 'parsing') {
    return (
      <div className="ov-pad" style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', minHeight: 420 }}>
        <p style={micro}>builder · parsing</p>
        <h2 className="ov-h1" style={{ marginTop: 12 }}>Splitting your resume into sections<span style={{ animation: 'ov-blink 1s steps(1,end) infinite' }}>_</span></h2>
        <div style={{ marginTop: 28, height: 14, border: '2px solid var(--ink)', overflow: 'hidden' }}>
          <div style={{ height: '100%', width: '40%', background: 'var(--ink)', animation: 'ov-indeterminate 1.1s ease-in-out infinite' }} />
        </div>
        <p style={{ ...micro, marginTop: 14 }}>one pass · faithful parse, never invents</p>
      </div>
    )
  }

  const active = doc.sections.find((s) => s.id === activeId) ?? doc.sections[0]
  return (
    <div className="ov-buildergrid" style={{ display: 'grid', gridTemplateColumns: '280px 1fr 440px', minHeight: 720, flex: 1 }}>
      <NavRail doc={doc} activeId={active?.id ?? ''} onPick={setActiveId} set={set} />
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '18px 24px', borderBottom: '2px solid var(--ink)', display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
            <span style={micro}>{active ? String(doc.sections.indexOf(active) + 1).padStart(2, '0') : '00'} / section</span>
            <input value={active?.label ?? ''} onChange={(e) => active && set(setLabel(dref.current, active.id, e.target.value))} disabled={active?.id === 'contact'}
              style={{ border: 0, background: 'transparent', fontSize: 24, fontWeight: 600, letterSpacing: '-0.02em', color: 'inherit', fontFamily: 'inherit', width: 260 }} />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <span style={micro}>confidence {Math.round((active?.conf ?? 1) * 100)}%</span>
            <button onClick={() => setPhase('import')} className="ov-btn">re-import</button>
          </div>
        </div>
        {active && active.issue && !active.reviewed && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '13px 24px', background: 'color-mix(in oklch, var(--honesty) 9%, transparent)', borderBottom: '2px solid var(--ink)' }}>
            <span style={{ width: 10, height: 10, flex: '0 0 10px', background: 'var(--honesty)' }} />
            <span style={{ ...micro, color: 'var(--honesty)' }}>review</span>
            <span style={{ flex: 1, fontSize: 14, lineHeight: 1.5 }}>{active.issue}</span>
            <button onClick={() => set(resolveIssue(dref.current, active.id))} className="ov-btn ov-btn-ink" style={{ whiteSpace: 'nowrap' }}>looks right</button>
          </div>
        )}
        {active && !active.on && active.id !== 'contact' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '12px 24px', background: 'var(--surface)', borderBottom: '2px solid var(--ink)' }}>
            <span style={{ ...micro }}>hidden</span>
            <span style={{ flex: 1, fontSize: 14, color: 'var(--dim)' }}>This section is off. It stays in your master CV and can be switched back on any time.</span>
            <button onClick={() => set(toggleSectionOn(dref.current, active.id))} className="ov-btn">show it</button>
          </div>
        )}
        <div style={{ padding: '24px', flex: 1 }}>{active && <SectionEditor sec={active} set={set} />}</div>
      </div>
      <PreviewPane doc={doc} onTailor={onTailor} />
    </div>
  )
}
