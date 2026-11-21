import { useState } from 'react'
import { Link } from 'react-router'
import { api, errorMessage, usePosts, type Post } from './api/client'

const PLATFORM_LABEL: Record<string, string> = { youtube: 'YouTube', facebook: 'Facebook' }
const POST_STATUS: Record<string, string> = {
  queued: 'antre',
  uploading: 'mengunggah',
  done: 'terunggah',
  failed: 'gagal',
}

const when = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' })
    : 'langsung'

export function PublishPanel({
  projectId,
  name,
  topic,
}: {
  projectId: string
  name: string
  topic: string | null
}) {
  const [posts, reload] = usePosts(projectId)
  const [platforms, setPlatforms] = useState<string[]>(['youtube'])
  const [title, setTitle] = useState(name)
  const [description, setDescription] = useState(topic ?? '')
  const [privacy, setPrivacy] = useState<'public' | 'unlisted' | 'private'>('public')
  const [at, setAt] = useState('')
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setStatus('')
    for (const platform of platforms) {
      const { error } = await api.POST('/api/v1/projects/{project_id}/posts', {
        params: { path: { project_id: projectId } },
        body: {
          platform: platform as 'youtube' | 'facebook',
          title,
          description,
          privacy,
          publish_at: at ? new Date(at).toISOString() : null,
        },
      })
      if (error) {
        setBusy(false)
        reload()
        return setStatus(`${PLATFORM_LABEL[platform]}: ${errorMessage(error)}`)
      }
    }
    setBusy(false)
    setStatus('Masuk antrean unggah.')
    reload()
  }

  return (
    <section aria-labelledby="publish-title">
      <h3 id="publish-title">Posting</h3>
      <form onSubmit={submit} className="discover-form">
        <fieldset className="row wrap">
          <legend className="sr-only">Platform</legend>
          {Object.entries(PLATFORM_LABEL).map(([p, label]) => (
            <label key={p}>
              <input
                type="checkbox"
                checked={platforms.includes(p)}
                onChange={() =>
                  setPlatforms(
                    platforms.includes(p) ? platforms.filter((x) => x !== p) : [...platforms, p],
                  )
                }
              />{' '}
              {label}
            </label>
          ))}
        </fieldset>
        <label htmlFor="post-title">Judul</label>
        <input
          id="post-title"
          maxLength={100}
          required
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <label htmlFor="post-description">Deskripsi</label>
        <textarea
          id="post-description"
          rows={3}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <div className="row wrap">
          <label>
            Tayang{' '}
            <input type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} />
          </label>
          <label>
            Privasi YouTube{' '}
            <select value={privacy} onChange={(e) => setPrivacy(e.target.value as typeof privacy)}>
              <option value="public">publik</option>
              <option value="unlisted">tidak publik</option>
              <option value="private">pribadi</option>
            </select>
          </label>
          <button type="submit" disabled={busy || platforms.length === 0}>
            {at ? 'Jadwalkan' : 'Unggah sekarang'}
          </button>
        </div>
        <p className="small muted">
          Video diunggah segera; bila ada jadwal, platform yang menayangkannya pada waktu itu.
        </p>
      </form>
      {status && <p role="status">{status}</p>}
      {posts && posts.length > 0 && <PostList posts={posts} onChange={reload} />}
    </section>
  )
}

export function PostList({
  posts,
  onChange,
  showProject = false,
}: {
  posts: Post[]
  onChange: () => void
  showProject?: boolean
}) {
  const act = async (post: Post, action: 'retry' | 'cancel') => {
    const path = { params: { path: { post_id: post.id } } }
    if (action === 'retry') await api.POST('/api/v1/posts/{post_id}/retry', path)
    else await api.DELETE('/api/v1/posts/{post_id}', path)
    onChange()
  }

  return (
    <ol className="list">
      {posts.map((p) => (
        <li key={p.id} className="row">
          <div>
            {showProject && (
              <>
                <Link to={`/projects/${p.project_id}?step=render`}>{p.project_name}</Link> ·{' '}
              </>
            )}
            <strong>{PLATFORM_LABEL[p.platform]}</strong> · {p.title}
            <div className="small muted">Tayang {when(p.publish_at)}</div>
            {p.error && <div className="small error">{p.error}</div>}
          </div>
          <div className="small job-when">
            <div className={`job-${p.status}`}>
              {POST_STATUS[p.status] ?? p.status}
              {p.status === 'uploading' && ` ${p.progress}%`}
            </div>
            {p.url && (
              <a href={p.url} target="_blank" rel="noreferrer">
                Buka
              </a>
            )}
            {p.status === 'failed' && (
              <button type="button" className="quiet small" onClick={() => act(p, 'retry')}>
                Ulangi
              </button>
            )}
            {(p.status === 'queued' || p.status === 'failed') && (
              <button type="button" className="quiet small" onClick={() => act(p, 'cancel')}>
                Batalkan
              </button>
            )}
          </div>
        </li>
      ))}
    </ol>
  )
}
