// Small app-level helpers, extracted from App.tsx.
import type { Job } from '@/lib/api'
import { ApiError } from '@/lib/api'

// Stable per-job key for the pending/enrichment set.
export const jobKey = (j: { platform: string; external_id: string }) => `${j.platform}:${j.external_id}`

// Ranking: a job with a description sorts by learned fit (else lexical relevance);
// jobs still lacking a description (e.g. LinkedIn-walled) sink below all rated ones
// rather than floating up on a misleading title-only relevance.
export const jobRank = (j: Job) => (j.has_description ? (j.fit ?? j.relevance ?? 0) : -1)

export function scoreColor(s: number): string {
  if (s >= 80) return 'var(--have)'
  if (s >= 60) return 'var(--ink)'
  if (s >= 40) return 'var(--gap)'
  return 'var(--honesty)'
}

export function err(e: unknown): string {
  if (e instanceof ApiError) return e.message
  const msg = e instanceof Error ? e.message : String(e)
  if (/failed to fetch|networkerror|load failed|err_connection/i.test(msg))
    return "Can't reach the server, make sure the backend is running, then try again."
  return msg
}

export function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

