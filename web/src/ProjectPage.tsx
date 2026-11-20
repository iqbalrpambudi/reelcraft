import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import {
  api,
  errorMessage,
  fileUrl,
  type Media,
  type Project,
  type Scene,
  type StepRun,
} from './api/client'

const STEP_LABEL: Record<string, string> = {
  ingest: 'Ambil media',
  analyze: 'Analisis scene',
  tag: 'Deskripsi AI',
}
const BUSY = ['reserved', 'queued', 'running']

const formatTime = (sec: number) =>
  `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, '0')}`

export function ProjectPage() {
  const { id = '' } = useParams()
  const [project, setProject] = useState<Project | null>()
  const [steps, setSteps] = useState<StepRun[]>([])
  const [media, setMedia] = useState<Media[]>([])
  const [scenes, setScenes] = useState<Scene[]>([])
  const [error, setError] = useState('')
  const [reloads, setReloads] = useState(0)
  const reload = () => setReloads((n) => n + 1)

  useEffect(() => {
    api
      .GET('/api/v1/projects/{project_id}', { params: { path: { project_id: id } } })
      .then(({ data }) => setProject(data ?? null))
  }, [id])

  // Live step status; also follows runs started from the CLI
  useEffect(() => {
    let lastStatuses = ''
    const source = new EventSource(`/api/v1/projects/${id}/events`)
    source.onmessage = (e) => {
      const next: StepRun[] = JSON.parse(e.data)
      setSteps(next)
      const statuses = next.map((s) => s.status).join()
      if (statuses !== lastStatuses) {
        lastStatuses = statuses
        reload() // a step finished or started: media/scenes may have changed
      }
    }
    return () => source.close()
  }, [id])

  useEffect(() => {
    const path = { project_id: id }
    api.GET('/api/v1/projects/{project_id}/media', { params: { path } }).then(({ data }) => {
      if (data) setMedia(data)
    })
    api.GET('/api/v1/projects/{project_id}/scenes', { params: { path } }).then(({ data }) => {
      if (data) setScenes(data)
    })
  }, [id, reloads])

  const path = { project_id: id }
  const busy = steps.some((s) => BUSY.includes(s.status))

  const run = async (start?: string) => {
    const { error } = await api.POST('/api/v1/projects/{project_id}/run', {
      params: { path },
      body: { start: start ?? null },
    })
    setError(error ? errorMessage(error) : '')
  }

  const cancel = () => api.POST('/api/v1/projects/{project_id}/cancel', { params: { path } })

  if (project === null) return <p>Project tidak ditemukan. <Link to="/">Kembali</Link></p>
  if (!project) return <p className="muted">Memuat...</p>

  return (
    <>
      <h1>{project.name}</h1>

      <section aria-labelledby="pipeline-title">
        <div className="row">
          <h2 id="pipeline-title">Pipeline</h2>
          {busy ? (
            <button type="button" className="quiet" onClick={cancel}>
              Batalkan
            </button>
          ) : (
            <button type="button" onClick={() => run()}>
              Jalankan
            </button>
          )}
        </div>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <ol className="steps">
          {steps.map((s) => (
            <li key={s.step} className={`step step-${s.status}`}>
              <div className="row">
                <strong>{STEP_LABEL[s.step] ?? s.step}</strong>
                <span className="badge">{s.status}</span>
              </div>
              {s.status === 'running' && (
                <progress max={100} value={s.progress} aria-label={`Progress ${s.step}`} />
              )}
              <div className="muted small">{s.error ?? s.message ?? ''}</div>
              {!busy && (
                <button type="button" className="quiet small" onClick={() => run(s.step)}>
                  Ulang dari sini
                </button>
              )}
            </li>
          ))}
        </ol>
      </section>

      <MediaPanel projectId={id} media={media} disabled={busy} onChange={reload} />

      <section aria-labelledby="scenes-title">
        <h2 id="scenes-title">Scene ({scenes.length})</h2>
        {scenes.length === 0 ? (
          <p className="muted">Scene muncul setelah step analisis selesai.</p>
        ) : (
          <ul className="scenes">
            {scenes.map((sc) => (
              <li key={sc.id}>
                {sc.thumbnail && (
                  <img src={fileUrl(id, sc.thumbnail)} alt="" loading="lazy" />
                )}
                <span className="small muted">
                  {formatTime(sc.start)}–{formatTime(sc.end)}
                </span>
                {sc.description ? (
                  <span className="small">{sc.description}</span>
                ) : (
                  sc.tag_error && <span className="small error">{sc.tag_error}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  )
}

function MediaPanel({
  projectId,
  media,
  disabled,
  onChange,
}: {
  projectId: string
  media: Media[]
  disabled: boolean
  onChange: () => void
}) {
  const [source, setSource] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const path = { project_id: projectId }

  const finish = (err: unknown) => {
    setBusy(false)
    setError(err ? errorMessage(err) : '')
    if (!err) onChange()
  }

  const addSource = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    const { error } = await api.POST('/api/v1/projects/{project_id}/media', {
      params: { path },
      body: { source },
    })
    if (!error) setSource('')
    finish(error)
  }

  const upload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setBusy(true)
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(`/api/v1/projects/${projectId}/media/upload`, {
      method: 'POST',
      body: form,
    })
    e.target.value = ''
    finish(res.ok ? undefined : await res.json())
  }

  const remove = async (m: Media) => {
    const { error } = await api.DELETE('/api/v1/projects/{project_id}/media/{media_id}', {
      params: { path: { ...path, media_id: m.id } },
    })
    finish(error)
  }

  return (
    <section aria-labelledby="media-title">
      <h2 id="media-title">Media</h2>
      <form onSubmit={addSource} className="row">
        <label htmlFor="media-source" className="sr-only">
          URL atau path file
        </label>
        <input
          id="media-source"
          placeholder="URL video (YouTube, dll.) atau path file di komputer ini"
          value={source}
          onChange={(e) => setSource(e.target.value)}
          required
        />
        <button type="submit" disabled={busy || disabled}>
          Tambah
        </button>
        <label className="button quiet">
          Unggah
          <input
            type="file"
            accept="video/*"
            className="sr-only"
            onChange={upload}
            disabled={busy || disabled}
          />
        </label>
      </form>
      {busy && <p className="muted small">Memproses...</p>}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <ul className="list">
        {media.map((m) => (
          <li key={m.id} className="row">
            <div>
              <div className="ellipsis">{m.source}</div>
              <div className="muted small">
                {m.status}
                {m.duration ? ` · ${formatTime(m.duration)}` : ''}
                {m.width ? ` · ${m.width}×${m.height}` : ''}
                {` · ${m.scene_count} scene`}
                {m.error ? ` · ${m.error}` : ''}
              </div>
            </div>
            <button
              type="button"
              className="quiet"
              onClick={() => remove(m)}
              disabled={disabled}
            >
              Hapus<span className="sr-only"> media</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
