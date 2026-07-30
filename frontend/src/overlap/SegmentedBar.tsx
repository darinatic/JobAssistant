/** The design's signature: progress as N discrete segments with a 1px gap, never
 *  a smooth fill. `filled = round(pct * segments)`; the segment right after the
 *  filled run pulses (ov-seg) so the bar reads as live between ticks. */
type Props = {
  segments: number
  pct: number // 0..1
  color?: string // filled color
  emptyColor?: string
  height?: number
  gap?: number
  /** pulse the leading (next-to-fill) segment; off when the bar is complete/idle */
  live?: boolean
}

export function SegmentedBar({
  segments,
  pct,
  color = 'var(--have)',
  emptyColor = 'var(--hair)',
  height = 8,
  gap = 2,
  live = true,
}: Props) {
  const clamped = Math.max(0, Math.min(1, pct))
  const filled = Math.round(clamped * segments)
  return (
    <div style={{ display: 'flex', gap, height, width: '100%' }} aria-hidden>
      {Array.from({ length: segments }, (_, i) => {
        const isFilled = i < filled
        const isLeading = live && i === filled && filled < segments
        return (
          <div
            key={i}
            style={{
              flex: 1,
              background: isFilled ? color : emptyColor,
              animation: isLeading ? 'ov-seg 0.65s ease-in-out infinite' : undefined,
              ...(isLeading ? { background: color } : null),
            }}
          />
        )
      })}
    </div>
  )
}
