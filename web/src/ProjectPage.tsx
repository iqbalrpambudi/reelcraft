import { useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import {
  api,
  errorMessage,
  fileUrl,
  type Media,
  type Project,
  type Scene,
  type StepRun,
  type Timeline,
  type Footage,
} from './api/client'
import { STATUS_LABEL, STEP_LABEL } from './labels'
import { PublishPanel } from './Posts'

const BUSY = ['reserved', 'queued', 'running']

const formatTime = (sec: number) =>
  `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, '0')}`

export function ProjectPage() {
  const { id = '' } = useParams()
  const [params, setParams] = useSearchParams()
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
  // Preview runs whatever is left up to it; if that's nothing, it runs again on its own
  const names = steps.map((s) => s.step)
  const pending = steps.find((s) => s.status !== 'done')?.step
  const previewFrom =
    pending && names.indexOf(pending) <= names.indexOf('preview') ? pending : 'preview'
  // The open segment: chosen in the URL, else what is happening now, else what is next
  const active = steps.find((s) => BUSY.includes(s.status))?.step
  const open = params.get('step') ?? active ?? pending ?? names[names.length - 1]
  const current = steps.find((s) => s.step === open)

  const run = async (start?: string, end?: string) => {
    const { error } = await api.POST('/api/v1/projects/{project_id}/run', {
      params: { path },
      body: { start: start ?? null, end: end ?? null },
    })
    setError(error ? errorMessage(error) : '')
  }

  const cancel = () => api.POST('/api/v1/projects/{project_id}/cancel', { params: { path } })

  if (project === null) return <p>Project tidak ditemukan. <Link to="/">Kembali</Link></p>
  if (!project) return <p className="muted">Memuat...</p>

  return (
    <>
      <div className="row">
        <h1>{project.name}</h1>
        {busy ? (
          <button type="button" className="quiet" onClick={cancel}>
            Batalkan
          </button>
        ) : (
          <div className="row">
            <button type="button" className="quiet" onClick={() => run(previewFrom, 'preview')}>
              Pratinjau
            </button>
            <button type="button" onClick={() => run()}>
              Jalankan
            </button>
          </div>
        )}
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}

      <nav aria-label="Segment pipeline">
        <ol className="steps">
          {steps.map((s, i) => (
            <li key={s.step}>
              <button
                type="button"
                className={`step step-${s.status}`}
                aria-current={s.step === open ? 'step' : undefined}
                onClick={() => setParams({ step: s.step }, { replace: true })}
              >
                <strong>
                  {i + 1}. {STEP_LABEL[s.step] ?? s.step}
                </strong>
                <span className="badge">{STATUS_LABEL[s.status] ?? s.status}</span>
                {s.status === 'running' && (
                  <progress max={100} value={s.progress} aria-label={`Progress ${s.step}`} />
                )}
              </button>
            </li>
          ))}
        </ol>
      </nav>

      {current && (
        <section aria-labelledby="segment-title" className="segment">
          <div className="row">
            <h2 id="segment-title">{STEP_LABEL[current.step] ?? current.step}</h2>
            {!busy && (
              <button type="button" className="quiet small" onClick={() => run(current.step)}>
                Jalankan ulang dari sini
              </button>
            )}
          </div>
          {(current.error || current.message) && (
            <p className={current.error ? 'error' : 'muted small'}>
              {current.error ?? current.message}
            </p>
          )}
          {current.step === 'ingest' && (
            <>
              <MediaPanel projectId={id} media={media} disabled={busy} onChange={reload} />
              <DiscoverPanel projectId={id} disabled={busy} onImported={reload} />
            </>
          )}
          {current.step === 'analyze' && <SceneGrid projectId={id} scenes={scenes} />}
          {current.step === 'tag' && <SceneGrid projectId={id} scenes={scenes} described />}
          {current.step === 'script' && (
            <ScriptPanel
              project={project}
              onProject={setProject}
              reloads={reloads}
              disabled={busy}
            />
          )}
          {current.step === 'voice' && <VoicePanel projectId={id} run={current} />}
          {current.step === 'edit' && (
            <TimelinePanel
              projectId={id}
              scenes={scenes}
              reloads={reloads}
              disabled={busy}
              onSaved={reload}
            />
          )}
          {(current.step === 'preview' || current.step === 'render') && (
            <VideoResult projectId={id} run={current} name={project.name} />
          )}
          {current.step === 'render' && current.status === 'done' && (
            <PublishPanel projectId={id} name={project.name} topic={project.topic} />
          )}
        </section>
      )}
    </>
  )
}

function SceneGrid({
  projectId,
  scenes,
  described = false,
}: {
  projectId: string
  scenes: Scene[]
  described?: boolean
}) {
  if (scenes.length === 0) return <p className="muted">Scene muncul setelah analisis selesai.</p>
  return (
    <ul className="scenes" aria-label={`${scenes.length} scene`}>
      {scenes.map((sc) => (
        <li key={sc.id}>
          {sc.thumbnail && <img src={fileUrl(projectId, sc.thumbnail)} alt="" loading="lazy" />}
          <span className="small muted">
            {formatTime(sc.start)}–{formatTime(sc.end)}
          </span>
          {described &&
            (sc.description ? (
              <>
                <span className="small">{sc.description}</span>
                <span className="small muted">{sc.tags?.join(', ')}</span>
              </>
            ) : (
              <span className="small error">{sc.tag_error ?? 'Belum dideskripsi'}</span>
            ))}
        </li>
      ))}
    </ul>
  )
}

type VoiceSegment = { text: string; start: number; end: number }

function VoicePanel({ projectId, run }: { projectId: string; run: StepRun }) {
  const [segments, setSegments] = useState<VoiceSegment[]>([])
  const audio = useRef<HTMLAudioElement>(null)
  const version = run.status === 'done' ? run.finished_at : null

  useEffect(() => {
    if (!version) return
    fetch(`${fileUrl(projectId, 'voice.json')}?v=${version}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => setSegments(data?.segments ?? []))
  }, [projectId, version])

  if (!version) return <p className="muted">Narasi muncul setelah step ini selesai.</p>
  const seek = (t: number) => {
    if (!audio.current) return
    audio.current.currentTime = t
    void audio.current.play()
  }
  return (
    <>
      <audio
        ref={audio}
        controls
        src={`${fileUrl(projectId, 'voice.wav')}?v=${version}`}
        aria-label="Narasi"
      />
      <ol className="list">
        {segments.map((seg, i) => (
          <li key={i}>
            <button type="button" className="quiet small" onClick={() => seek(seg.start)}>
              {formatTime(seg.start)}
            </button>{' '}
            {seg.text}
          </li>
        ))}
      </ol>
    </>
  )
}

function VideoResult({ projectId, run, name }: { projectId: string; run: StepRun; name: string }) {
  if (run.status !== 'done') return <p className="muted">Video muncul setelah step ini selesai.</p>
  const url = `${fileUrl(projectId, `${run.step}.mp4`)}?v=${run.finished_at}`
  return (
    <>
      <video controls className="result" src={url} aria-label={`Video ${run.step}`} />
      {run.step === 'render' && (
        <p>
          <a href={url} download={`${name}.mp4`}>
            Unduh video
          </a>
        </p>
      )}
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
      <h3 id="media-title">Media</h3>
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
              {m.file && (
                <details>
                  <summary className="small">Putar</summary>
                  <video
                    controls
                    preload="none"
                    className="result"
                    src={fileUrl(projectId, m.file)}
                    aria-label={`Media ${m.source}`}
                  />
                </details>
              )}
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
  reloads,
  disabled,
}: {
  project: Project
  onProject: (p: Project) => void
  reloads: number
  disabled: boolean
}) {
  const [templates, setTemplates] = useState<Record<string, string>>({})
  const [brief, setBrief] = useState({
    topic: project.topic ?? '',
    template: project.template,
    instructions: project.instructions ?? '',
    music: project.music ?? '',
  })
  const [moods, setMoods] = useState<string[]>([])
  const [text, setText] = useState('')
  const [savedText, setSavedText] = useState('')
  const saved = useRef('')
  const [status, setStatus] = useState('')
  const path = { project_id: project.id }

  useEffect(() => {
    api.GET('/api/v1/templates').then(({ data }) => setTemplates(data ?? {}))
    api.GET('/api/v1/music').then(({ data }) => setMoods(data ?? []))
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
      <h3 id="script-title">Bahan naskah</h3>
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
        <div className="field">
          <label htmlFor="brief-music">Musik latar</label>
          <select
            id="brief-music"
            value={brief.music}
            onChange={(e) => setBrief({ ...brief, music: e.target.value })}
          >
            <option value="">Tanpa musik</option>
            {moods.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
          <span className="small muted">
            Mood = folder lagu di data dir, <code>music/&lt;mood&gt;/</code>.
          </span>
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

    </section>
  )
}

function TimelinePanel({
  projectId,
  scenes,
  reloads,
  disabled,
  onSaved,
}: {
  projectId: string
  scenes: Scene[]
  reloads: number
  disabled: boolean
  onSaved: () => void
}) {
  const [timeline, setTimeline] = useState<Timeline | null>(null)
  const [order, setOrder] = useState<number[]>([])
  const [status, setStatus] = useState('')

  useEffect(() => {
    const path = { project_id: projectId }
    api.GET('/api/v1/projects/{project_id}/timeline', { params: { path } }).then(({ data }) => {
      setTimeline(data ?? null)
      setOrder(data ? data.clips.map((_, i) => i) : [])
    })
  }, [projectId, reloads])

  if (!timeline || timeline.clips.length === 0) return null
  const thumbs = Object.fromEntries(scenes.map((sc) => [sc.id, sc.thumbnail]))
  const changed = order.some((clip, i) => clip !== i)

  const move = (i: number, by: number) => {
    const next = [...order]
    ;[next[i], next[i + by]] = [next[i + by], next[i]]
    setOrder(next)
  }

  const save = async () => {
    const { data, error } = await api.PUT('/api/v1/projects/{project_id}/timeline', {
      params: { path: { project_id: projectId } },
      body: { order },
    })
    if (data) {
      setTimeline(data)
      setOrder(data.clips.map((_, i) => i))
      onSaved()
    }
    setStatus(error ? errorMessage(error) : 'Urutan disimpan. Jalankan pratinjau untuk melihat.')
  }

  return (
    <section aria-labelledby="timeline-title">
      <div className="row">
        <h3 id="timeline-title">Timeline ({timeline.clips.length} klip)</h3>
        <button type="button" onClick={save} disabled={disabled || !changed}>
          Simpan urutan
        </button>
      </div>
      <p className="muted small">
        Narasi tetap di tempatnya; tombol naik/turun menukar footage yang tampil.
      </p>
      {status && <p role="status">{status}</p>}
      <ol className="list">
        {order.map((clipIndex, i) => {
          const slot = timeline.clips[i]
          const footage = timeline.clips[clipIndex]
          const thumb = thumbs[footage.scene_id]
          return (
            <li key={clipIndex} className="row timeline-clip">
              {thumb ? <img src={fileUrl(projectId, thumb)} alt="" /> : <span />}
              <div>
                <div className="small muted">
                  {formatTime(slot.start)}–{formatTime(slot.end)}
                </div>
                <div className="small">{slot.text}</div>
              </div>
              <div className="row">
                <button
                  type="button"
                  className="quiet small"
                  onClick={() => move(i, -1)}
                  disabled={disabled || i === 0}
                  aria-label={`Naikkan klip ${i + 1}`}
                >
                  ↑
                </button>
                <button
                  type="button"
                  className="quiet small"
                  onClick={() => move(i, 1)}
                  disabled={disabled || i === order.length - 1}
                  aria-label={`Turunkan klip ${i + 1}`}
                >
                  ↓
                </button>
              </div>
            </li>
          )
        })}
      </ol>
    </section>
  )
}

const SOURCES = ['youtube', 'pexels', 'pixabay', 'archive'] as const
const SOURCE_LABEL: Record<string, string> = {
  youtube: 'YouTube',
  pexels: 'Pexels',
  pixabay: 'Pixabay',
  archive: 'Archive.org',
}

function DiscoverPanel({
  projectId,
  disabled,
  onImported,
}: {
  projectId: string
  disabled: boolean
  onImported: () => void
}) {
  const [query, setQuery] = useState('')
  const [sources, setSources] = useState<string[]>([...SOURCES])
  const [minDuration, setMinDuration] = useState('')
  const [maxDuration, setMaxDuration] = useState('')
  const [freeOnly, setFreeOnly] = useState(false)
  const [hideImported, setHideImported] = useState(true)
  const [results, setResults] = useState<Footage[]>()
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [picked, setPicked] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState('')
  const path = { project_id: projectId }

  const search = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setStatus('')
    const { data, error } = await api.GET('/api/v1/projects/{project_id}/discover', {
      params: {
        path,
        query: {
          q: query,
          sources,
          min_duration: minDuration ? Number(minDuration) : null,
          max_duration: maxDuration ? Number(maxDuration) : null,
          free_only: freeOnly,
          hide_imported: hideImported,
        },
      },
    })
    setBusy(false)
    setResults(data?.results)
    setErrors(data?.errors ?? {})
    setPicked([])
    if (error) setStatus(errorMessage(error))
  }

  const importPicked = async () => {
    setBusy(true)
    const { error } = await api.POST('/api/v1/projects/{project_id}/media/batch', {
      params: { path },
      body: { sources: picked },
    })
    setBusy(false)
    if (error) return setStatus(errorMessage(error))
    setResults(results?.map((r) => (picked.includes(r.url) ? { ...r, imported: true } : r)))
    setStatus(`${picked.length} klip ditambahkan. Jalankan untuk mengunduh.`)
    setPicked([])
    onImported()
  }

  const toggle = <T,>(list: T[], item: T) =>
    list.includes(item) ? list.filter((x) => x !== item) : [...list, item]

  return (
    <section aria-labelledby="discover-title">
      <h3 id="discover-title">Cari footage</h3>
      <form onSubmit={search} className="discover-form">
        <div className="row">
          <label htmlFor="discover-q" className="sr-only">
            Kata kunci
          </label>
          <input
            id="discover-q"
            placeholder="Kata kunci, mis. pembuatan keris"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            required
          />
          <button type="submit" disabled={busy || sources.length === 0}>
            {busy ? 'Mencari...' : 'Cari'}
          </button>
        </div>
        <fieldset className="row wrap">
          <legend className="sr-only">Sumber</legend>
          {SOURCES.map((src) => (
            <label key={src} className="small">
              <input
                type="checkbox"
                checked={sources.includes(src)}
                onChange={() => setSources(toggle(sources, src))}
              />{' '}
              {SOURCE_LABEL[src]}
            </label>
          ))}
        </fieldset>
        <div className="row wrap small">
          <label>
            Durasi{' '}
            <input
              type="number"
              min={0}
              className="narrow"
              placeholder="min"
              aria-label="Durasi minimum (detik)"
              value={minDuration}
              onChange={(e) => setMinDuration(e.target.value)}
            />
            –
            <input
              type="number"
              min={0}
              className="narrow"
              placeholder="maks"
              aria-label="Durasi maksimum (detik)"
              value={maxDuration}
              onChange={(e) => setMaxDuration(e.target.value)}
            />{' '}
            detik
          </label>
          <label>
            <input type="checkbox" checked={freeOnly} onChange={() => setFreeOnly(!freeOnly)} />{' '}
            Hanya lisensi bebas (boleh diedit & dimonetisasi)
          </label>
          <label>
            <input
              type="checkbox"
              checked={hideImported}
              onChange={() => setHideImported(!hideImported)}
            />{' '}
            Sembunyikan yang sudah diimpor
          </label>
        </div>
      </form>
      {Object.entries(errors).map(([src, message]) => (
        <p key={src} className="small error">
          {SOURCE_LABEL[src] ?? src}: {message}
        </p>
      ))}
      {status && <p role="status">{status}</p>}
      {results && results.length === 0 && <p className="muted">Tidak ada hasil.</p>}
      {results && results.length > 0 && (
        <>
          <div className="row">
            <span className="small muted">{results.length} hasil</span>
            <button
              type="button"
              onClick={importPicked}
              disabled={disabled || busy || picked.length === 0}
            >
              Impor {picked.length || ''} klip
            </button>
          </div>
          <ul className="footage">
            {results.map((f) => (
              <li key={f.url}>
                <label>
                  {f.thumbnail && <img src={f.thumbnail} alt="" loading="lazy" />}
                  <input
                    type="checkbox"
                    checked={picked.includes(f.url)}
                    disabled={f.imported}
                    onChange={() => setPicked(toggle(picked, f.url))}
                  />{' '}
                  <strong className="small">{f.title}</strong>
                </label>
                <span className="small muted">
                  {SOURCE_LABEL[f.source]}
                  {f.duration ? ` · ${formatTime(f.duration)}` : ''}
                  {f.author ? ` · ${f.author}` : ''}
                </span>
                <span className={`small ${f.free ? 'free' : 'muted'}`}>
                  {f.free ? 'Lisensi bebas' : f.license}
                  {f.imported && ' · sudah diimpor'}
                </span>
                <a className="small" href={f.page} target="_blank" rel="noreferrer">
                  Buka sumber
                </a>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
