import createClient from 'openapi-fetch'
import type { components, paths } from './schema'

// Same origin: served by `reelcraft serve`, or proxied by Vite in development
export const api = createClient<paths>()

type Schemas = components['schemas']
export type Project = Schemas['ProjectOut']
export type Media = Schemas['MediaOut']
export type Scene = Schemas['SceneOut']
export type StepRun = Schemas['StepRunOut']
export type SettingItem = Schemas['SettingOut']
export type AICheck = Schemas['AICheck']

/** URL of a file inside a project's data dir (thumbnails, media, renders). */
export const fileUrl = (projectId: string, path: string) =>
  `/api/v1/projects/${projectId}/files/${path}`

/** Our handler returns `detail` as a string; FastAPI validation errors return a list. */
export function errorMessage(error: unknown): string {
  const detail = (error as { detail?: unknown } | undefined)?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d: { msg: string }) => d.msg).join(', ')
  return 'Terjadi kesalahan'
}
