import { useEffect, useRef, useState } from 'react'
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
  script: 'Naskah',
  voice: 'Suara',
  edit: 'Susun klip',
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

      <ScriptPanel
        project={project}
        onProject={setProject}
        voice={steps.find((s) => s.step === 'voice')}
        reloads={reloads}
        disabled={busy}
      />

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

function ScriptPanel({
  project,
  onProject,
  voice,
  reloads,
  disabled,
}: {
  project: Project
  onProject: (p: Project) => void
  voice?: StepRun
  reloads: number
  disabled: boolean
}) {
  const [templates, setTemplates] = useState<Record<string, string>>({})
  const [brief, setBrief] = useState({
    topic: project.topic ?? '',
    template: project.template,
    instructions: project.instructions ?? '',
  })
  const [text, setText] = useState('')
  const [savedText, setSavedText] = useState('')
  const saved = useRef('')
  const [status, setStatus] = useState('')
  const path = { project_id: project.id }

  useEffect(() => {
    api.GET('/api/v1/templates').then(({ data }) => setTemplates(data ?? {}))
  }, [])

  // Pick up a script the pipeline (re)wrote, unless the user has unsaved edits
  useEffect(() => {
    const path = { project_id: project.id }
    api.GET('/api/v1/projects/{project_id}/script', { params: { path } }).then(({ data }) => {
      const next = data?.text ?? ''
      const prev = saved.current
      saved.current = next
      setSavedText(next)
      setText((current) => (current === prev ? next : current))
    })
  }, [project.id, reloads])

  const saveBrief = async (e: React.FormEvent) => {
    e.preventDefault()
    const { data, error } = await api.PATCH('/api/v1/projects/{project_id}', {
      params: { path },
      body: brief,
    })
    if (data) onProject(data)
    setStatus(error ? errorMessage(error) : 'Bahan naskah disimpan.')
  }

  const saveScript = async () => {
    const { data, error } = await api.PUT('/api/v1/projects/{project_id}/script', {
      params: { path },
      body: { text },
    })
    if (data) {
      saved.current = data.text ?? ''
      setText(saved.current)
      setSavedText(saved.current)
    }
    setStatus(error ? errorMessage(error) : 'Naskah disimpan. Jalankan lagi untuk membuat suara.')
  }

  return (
    <section aria-labelledby="script-title">
      <h2 id="script-title">Naskah & suara</h2>
      <form onSubmit={saveBrief} className="settings">
        <div className="field">
          <label htmlFor="brief-topic">Topik</label>
          <input
            id="brief-topic"
            placeholder="Kosongkan agar AI menentukan dari scene"
            value={brief.topic}
            onChange={(e) => setBrief({ ...brief, topic: e.target.value })}
          />
        </div>
        <div className="field">
          <label htmlFor="brief-template">Template</label>
          <select
            id="brief-template"
            value={brief.template}
            onChange={(e) => setBrief({ ...brief, template: e.target.value })}
          >
            {Object.keys(templates).map((key) => (
              <option key={key} value={key}>
                {key}
              </option>
            ))}
          </select>
          <span className="small muted">
            {templates[brief.template] || 'Pakai instruksi di bawah.'}
          </span>
        </div>
        <div className="field">
          <label htmlFor="brief-instructions">Instruksi tambahan</label>
          <textarea
            id="brief-instructions"
            rows={2}
            value={brief.instructions}
            onChange={(e) => setBrief({ ...brief, instructions: e.target.value })}
          />
        </div>
        <div>
          <button type="submit" disabled={disabled}>
            Simpan bahan
          </button>
        </div>
      </form>

      <div className="field">
        <label htmlFor="script-text">Naskah</label>
        <textarea
          id="script-text"
          rows={10}
          placeholder={'# Judul\n\nParagraf pertama narasi.\n\nParagraf kedua.'}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <span className="small muted">
          Baris pertama judul (# ...), lalu satu paragraf per segmen.
        </span>
      </div>
      <button type="button" onClick={saveScript} disabled={disabled || text === savedText}>
        Simpan naskah
      </button>
      {status && <p role="status">{status}</p>}

      {voice?.status === 'done' && (
        <audio
          controls
          src={`${fileUrl(project.id, 'voice.wav')}?v=${voice.finished_at}`}
          aria-label="Narasi"
        />
      )}
    </section>
  )
}
