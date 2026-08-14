// What each board can actually filter, as published by GET /search/capabilities.
// Drives the greying of filters no selected board can honour, so the UI stops
// accepting a click and silently dropping the filter.
//
// Pure on purpose: the fetch lives in api.ts with the other requests, leaving
// this module trivially testable.

export type Support = 'native' | 'local' | 'unsupported'

export type BoardCaps = {
  common: Record<string, Support>
  notes: Record<string, string>
  native_filters: Record<string, unknown> | null
}

export type Capabilities = {
  boards: Record<string, BoardCaps>
  vocabularies: Record<string, string[]>
}

/** Per-platform record of which requested filters a board honoured. */
export type FilterReport = Record<string, { applied: string[]; dropped: Record<string, string> }>

/** Can this filter do anything for the selected boards, and if not, why not?
 *  An empty selection means every board. Fails open while capabilities load, so a
 *  slow or failed fetch never blocks a filter the user could legitimately use. */
export function filterSupport(
  caps: Capabilities | null,
  platforms: string[],
  key: string,
): { usable: boolean; reason: string } {
  if (!caps) return { usable: true, reason: '' }
  const selected = platforms.length ? platforms : Object.keys(caps.boards)
  const reasons: string[] = []
  for (const p of selected) {
    const support = caps.boards[p]?.common?.[key]
    if (support === 'native' || support === 'local') return { usable: true, reason: '' }
    const note = caps.boards[p]?.notes?.[key]
    if (note) reasons.push(note)
  }
  return { usable: false, reason: reasons[0] ?? 'No selected board supports this filter.' }
}

/** One line naming every filter a board could not honour, or '' when none were. */
export function droppedSummary(report: FilterReport | null): string {
  if (!report) return ''
  const parts = Object.entries(report).flatMap(([board, r]) =>
    Object.keys(r?.dropped ?? {}).map((k) => `${board} ignored ${k.replace(/_/g, ' ')}`),
  )
  if (!parts.length) return ''
  return `Note: ${parts.join(', ')}. Use refine below to narrow these results instead.`
}
