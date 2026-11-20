import createClient from 'openapi-fetch'
import type { components, paths } from './schema'

// Same origin: served by `reelcraft serve`, or proxied by Vite in development
export const api = createClient<paths>()

export type Project = components['schemas']['ProjectOut']

/** Our handler returns `detail` as a string; FastAPI validation errors return a list. */
export function errorMessage(error: unknown): string {
  const detail = (error as { detail?: unknown } | undefined)?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d: { msg: string }) => d.msg).join(', ')
  return 'Terjadi kesalahan'
}
