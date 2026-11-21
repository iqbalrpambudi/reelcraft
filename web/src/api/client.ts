import { useEffect, useState } from 'react'
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
export type Timeline = Schemas['Timeline']
export type ActiveStep = Schemas['ActiveStep']
export type Job = Schemas['JobOut']
export type Footage = Schemas['FootageOut']
export type Account = Schemas['AccountOut']
export type Post = Schemas['PostOut']

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

const QUEUE_POLL_MS = 3000

/** Steps running or waiting across all projects, refreshed every few seconds. */
export function useQueue(): ActiveStep[] {
  const [queue, setQueue] = useState<ActiveStep[]>([])
  useEffect(() => {
    let alive = true
    const load = () =>
      api.GET('/api/v1/queue').then(({ data }) => {
        if (alive && data) setQueue(data)
      })
    load()
    const timer = setInterval(load, QUEUE_POLL_MS)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [])
  return queue
}

/** Posts, newest first, refreshed every few seconds while uploads go out. */
export function usePosts(projectId?: string): [Post[] | undefined, () => void] {
  const [posts, setPosts] = useState<Post[]>()
  const [tick, setTick] = useState(0)
  useEffect(() => {
    let alive = true
    const load = () =>
      api
        .GET('/api/v1/posts', { params: { query: { project_id: projectId } } })
        .then(({ data }) => {
          if (alive && data) setPosts(data)
        })
    load()
    const timer = setInterval(load, QUEUE_POLL_MS)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [projectId, tick])
  return [posts, () => setTick((t) => t + 1)]
}
