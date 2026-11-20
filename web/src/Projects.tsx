import { useEffect, useState } from 'react'
import { api, errorMessage, type Project } from './api/client'

export function Projects() {
  const [projects, setProjects] = useState<Project[]>()
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const [reloads, setReloads] = useState(0)
  const reload = () => setReloads((n) => n + 1)

  useEffect(() => {
    api.GET('/api/v1/projects').then(({ data, error }) => {
      if (error) setError(errorMessage(error))
      else setProjects(data)
    })
  }, [reloads])

  const create = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    const { error } = await api.POST('/api/v1/projects', { body: { name } })
    setBusy(false)
    if (error) return setError(errorMessage(error))
    setName('')
    setError('')
    reload()
  }

  const remove = async (p: Project) => {
    if (!confirm(`Hapus project "${p.name}"?`)) return
    const { error } = await api.DELETE('/api/v1/projects/{project_id}', {
      params: { path: { project_id: p.id } },
    })
    if (error) return setError(errorMessage(error))
    reload()
  }

  return (
    <section aria-labelledby="projects-title">
      <h2 id="projects-title">Project</h2>

      <form onSubmit={create} className="row">
        <label htmlFor="project-name" className="sr-only">
          Nama project
        </label>
        <input
          id="project-name"
          placeholder="Nama project baru"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={200}
          required
        />
        <button type="submit" disabled={busy}>
          Buat
        </button>
      </form>

      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}

      {projects === undefined ? (
        <p className="muted">Memuat...</p>
      ) : projects.length === 0 ? (
        <p className="muted">Belum ada project.</p>
      ) : (
        <ul className="list">
          {projects.map((p) => (
            <li key={p.id} className="row">
              <div>
                <strong>{p.name}</strong>
                <div className="muted small">
                  {p.id.slice(0, 8)} · dibuat {new Date(p.created_at).toLocaleString()}
                </div>
              </div>
              <button type="button" className="quiet" onClick={() => remove(p)}>
                Hapus<span className="sr-only"> {p.name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
