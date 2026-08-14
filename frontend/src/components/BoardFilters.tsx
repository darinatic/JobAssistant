// Board-native filters, shown only when exactly one board is selected. An agency
// filter is meaningless across a mixed selection, and four boards' worth of
// controls at once would bury the shared filters above them.
import { FilterRow, FilterBtn } from '@/components/SearchFilters'
import type { Capabilities } from '@/lib/capabilities'

const LABELS: Record<string, string> = {
  careersgov: 'Careers@Gov',
  mycareersfuture: 'MyCareersFuture',
  jobstreet: 'JobStreet',
  linkedin: 'LinkedIn',
}

// Which vocabulary feeds which field, and how the row is labelled.
const ROWS: Record<string, { field: string; label: string; vocab: string }[]> = {
  careersgov: [
    { field: 'agencies', label: 'agency', vocab: 'careersgov_agencies' },
    { field: 'departments', label: 'function', vocab: 'careersgov_departments' },
    { field: 'employment_types', label: 'contract', vocab: 'careersgov_employment_types' },
  ],
  mycareersfuture: [
    { field: 'categories', label: 'category', vocab: 'mcf_categories' },
    { field: 'employment_types', label: 'contract', vocab: 'mcf_employment_types' },
  ],
  jobstreet: [
    { field: 'work_types', label: 'work type', vocab: 'jobstreet_work_types' },
  ],
  linkedin: [],
}

export function BoardFilters({ caps, platform, value, onChange }: {
  caps: Capabilities | null
  platform: string
  value: Record<string, unknown>
  onChange: (next: Record<string, unknown>) => void
}) {
  const rows = ROWS[platform] ?? []
  if (!caps || rows.length === 0) return null

  const toggle = (field: string, v: string) => {
    const current = (value[field] as string[]) ?? []
    const next = current.includes(v) ? current.filter((x) => x !== v) : [...current, v]
    onChange({ ...value, [field]: next })
  }

  return (
    <div style={{ borderTop: '1px solid var(--rule)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', background: 'var(--panel)', borderBottom: '1px solid var(--rule)', flexWrap: 'wrap' }}>
        <span className="ov-micro" style={{ fontSize: 9, color: 'var(--ink)' }}>
          ▸ {LABELS[platform] ?? platform} filters
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--dim)' }}>
          only this board supports these
        </span>
      </div>
      {rows.map((row) => {
        const options = caps.vocabularies[row.vocab] ?? []
        if (options.length === 0) return null
        const selected = (value[row.field] as string[]) ?? []
        return (
          <FilterRow key={row.field} label={row.label}
            note={options.length > 24 ? `${options.length} options` : undefined}>
            <div style={{ display: 'flex', flexWrap: 'wrap', maxHeight: 116, overflowY: 'auto' }}>
              {options.map((o) => (
                <FilterBtn key={o} active={selected.includes(o)} onClick={() => toggle(row.field, o)}>
                  {o}
                </FilterBtn>
              ))}
            </div>
          </FilterRow>
        )
      })}
    </div>
  )
}
