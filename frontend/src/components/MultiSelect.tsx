// Searchable multi-select for the long board-native vocabularies (96 agencies,
// 36 departments, 32 categories). Short vocabularies keep their chip rows: for
// four or eight options a dropdown hides what a glance would have shown.
//
// Hand-rolled rather than shadcn: the set here has no `command`/`popover`, Radix's
// DropdownMenu captures keystrokes for typeahead and so fights a search input, and
// the surrounding filter controls are already plain inline-styled elements.
import { useEffect, useMemo, useRef, useState } from 'react'

/** Options whose selected values are shown as chips OUTSIDE the collapsed control.
 *  Not decoration: a filter that is active while invisible is the exact failure the
 *  capability layer exists to prevent, and collapsing the panel must not recreate it. */
export function matchesQuery(option: string, query: string, aliases?: Record<string, string>): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  if (option.toLowerCase().includes(q)) return true
  // Acronym search: the board lists agencies only by full legal name, so "htx"
  // must find "Home Team Science and Technology Agency (HTX)".
  if (!aliases) return false
  return Object.entries(aliases).some(([short, full]) => full === option && short.includes(q))
}

export function MultiSelect({ label, options, selected, onChange, aliases }: {
  label: string
  options: string[]
  selected: string[]
  onChange: (next: string[]) => void
  aliases?: Record<string, string>
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const box = useRef<HTMLDivElement>(null)

  // Close on outside click / Escape, so an open panel never obscures the filters.
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const shown = useMemo(
    () => options.filter((o) => matchesQuery(o, query, aliases)),
    [options, query, aliases],
  )

  const toggle = (v: string) =>
    onChange(selected.includes(v) ? selected.filter((x) => x !== v) : [...selected, v])

  const mono = { fontFamily: 'var(--font-mono)', fontSize: 11 } as const

  return (
    <div ref={box} style={{ flex: 1, minWidth: 0 }}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="ov-mono"
        style={{
          ...mono, width: '100%', textAlign: 'left', padding: '8px 12px',
          background: 'transparent', border: 'none', borderRight: '1px solid var(--rule)',
          cursor: 'pointer', color: selected.length ? 'var(--ink)' : 'var(--dim)',
          fontWeight: selected.length ? 700 : 400,
        }}
      >
        {selected.length ? `${selected.length} selected` : `all ${options.length}`} {open ? '▴' : '▾'}
      </button>

      {/* Selected values stay visible when the panel is shut. */}
      {selected.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, padding: '6px 12px', borderTop: '1px solid var(--rule)' }}>
          {selected.map((v) => (
            <button
              key={v}
              onClick={() => toggle(v)}
              title={`remove ${v}`}
              className="ov-mono"
              style={{
                ...mono, fontSize: 10, padding: '2px 6px', cursor: 'pointer',
                background: 'var(--ink)', color: 'var(--paper)', border: 'none',
                maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}
            >
              {v} ✕
            </button>
          ))}
        </div>
      )}

      {/* In flow, not absolutely positioned. An overlay covered the rows below but
          NOT their labels, so the search box read as belonging to the next row down.
          Letting the panel push subsequent rows down keeps every label aligned with
          its own control, and needs no z-index. */}
      {open && (
        <div
          style={{
            borderTop: '1px solid var(--rule)', borderBottom: '2px solid var(--ink)',
            background: 'var(--paper)', maxHeight: 260,
            display: 'flex', flexDirection: 'column',
          }}
        >
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={`search ${options.length} ${label}`}
            className="ov-mono"
            style={{ ...mono, padding: '8px 12px', border: 'none', borderBottom: '1px solid var(--rule)', outline: 'none', background: 'transparent' }}
          />
          <div style={{ overflowY: 'auto' }}>
            {shown.length === 0 && (
              <div className="ov-micro" style={{ fontSize: 9, padding: '10px 12px', color: 'var(--dim)' }}>
                no match for "{query}"
              </div>
            )}
            {shown.map((o) => {
              const on = selected.includes(o)
              return (
                <button
                  key={o}
                  onClick={() => toggle(o)}
                  className="ov-mono"
                  style={{
                    ...mono, display: 'flex', gap: 8, width: '100%', textAlign: 'left',
                    padding: '6px 12px', cursor: 'pointer', border: 'none',
                    background: on ? 'color-mix(in oklab, var(--ink) 8%, transparent)' : 'transparent',
                    color: on ? 'var(--ink)' : 'var(--dim)', fontWeight: on ? 700 : 400,
                  }}
                >
                  <span aria-hidden style={{ width: 10 }}>{on ? '■' : '□'}</span>
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{o}</span>
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
