import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { api, errorMessage, usePosts, useQueue, type Autopilot, type Job } from './api/client'
import { STATUS_LABEL, STEP_LABEL } from './labels'
import { PostList } from './Posts'

const when = (iso: string) =>
  new Date(iso).toLocaleString('id-ID', { dateStyle: 'short', timeStyle: 'short' })

const took = (job: Job) => {
  if (!job.finished_at) return ''
  const sec = (Date.parse(job.finished_at) - Date.parse(job.started_at)) / 1000
  return sec < 60 ? `${Math.round(sec)} dtk` : `${Math.round(sec / 60)} mnt`
}

export function JobsPage() {
  const queue = useQueue()
  const [posts, reloadPosts] = usePosts()
  const [jobs, setJobs] = useState<Job[]>()
  const queueKey = queue.map((q) => `${q.project_id}:${q.step}:${q.status}`).join()

  // History changes when something starts or ends, which is when the queue changes
  useEffect(() => {
    api.GET('/api/v1/jobs').then(({ data }) => setJobs(data))
  }, [queueKey])

  return (
    <>
      <h1>Jobs</h1>
      <section aria-labelledby="queue-title">
        <h2 id="queue-title">Antrean</h2>
        {queue.length === 0 ? (
          <p className="muted">Tidak ada yang berjalan atau menunggu.</p>
        ) : (
          <ol className="list">
            {queue.map((q) => (
              <li key={`${q.project_id}-${q.step}`} className="row">
                <div>
                  <Link to={`/projects/${q.project_id}?step=${q.step}`}>{q.project_name}</Link>
                  <span className="muted"> · {STEP_LABEL[q.step] ?? q.step}</span>
                  {q.message && <div className="muted small">{q.message}</div>}
                </div>
                <span className="small">
                  {STATUS_LABEL[q.status] ?? q.status}
                  {q.status === 'running' && ` ${q.progress}%`}
                </span>
              </li>
            ))}
          </ol>
        )}
      </section>

      <AutopilotPanel refreshKey={queueKey} />

      <section aria-labelledby="posts-title">
        <h2 id="posts-title">Posting</h2>
        {posts?.length ? (
          <PostList posts={posts} onChange={reloadPosts} showProject />
        ) : (
          <p className="muted">Belum ada posting.</p>
        )}
      </section>

      <section aria-labelledby="history-title">
        <h2 id="history-title">Riwayat</h2>
        {!jobs ? (
          <p className="muted">Memuat...</p>
        ) : jobs.length === 0 ? (
          <p className="muted">Belum ada run.</p>
        ) : (
          <ol className="list">
            {jobs.map((j) => (
              <li key={j.id} className="row">
                <div>
                  <Link to={`/projects/${j.project_id}?step=${j.step ?? j.steps[0]}`}>
                    {j.project_name}
                  </Link>
                  <span className="muted small">
                    {' '}
                    ·{' '}
                    {j.steps
                      .map((st) => STEP_LABEL[st] ?? st)
                      .filter((_, i, all) => i === 0 || i === all.length - 1)
                      .join(' → ')}
                  </span>
                  {j.error && (
                    <div className="error small">
                      {STEP_LABEL[j.step ?? ''] ?? j.step}: {j.error}
                    </div>
                  )}
                </div>
                <div className="small job-when">
                  <div className={`job-${j.status}`}>{STATUS_LABEL[j.status] ?? j.status}</div>
                  <div className="muted">
                    {when(j.started_at)} {took(j) && `· ${took(j)}`}
                  </div>
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>
    </>
  )
}

const POOL_STATE: Record<string, string> = {
  producing: 'diproduksi',
  ready: 'siap, menunggu slot',
  failed: 'gagal',
}

function AutopilotPanel({ refreshKey }: { refreshKey: string }) {
  const [status, setStatus] = useState<Autopilot>()
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const load = () =>
    api.GET('/api/v1/autopilot').then(({ data, error }) => {
      setStatus(data)
      if (error) setMessage(errorMessage(error))
    })
  useEffect(() => {
    load()
  }, [refreshKey])

  const produce = async () => {
    setBusy(true)
    setMessage('Mencari ide dan footage...')
    const { error } = await api.POST('/api/v1/autopilot/produce')
    setBusy(false)
    setMessage(error ? errorMessage(error) : 'Video baru masuk antrean.')
    load()
  }

  return (
    <section aria-labelledby="autopilot-title">
      <div className="row">
        <h2 id="autopilot-title">Autopilot</h2>
        <button type="button" className="quiet" onClick={produce} disabled={busy}>
          Buat video sekarang
        </button>
      </div>
      {status && (
        <>
          <p className="small">
            <strong>{status.enabled ? 'Aktif' : 'Mati'}</strong>
            {' · '}
            {status.platforms.length
              ? `posting ke ${status.platforms.join(', ')}`
              : 'belum ada akun terhubung'}
            {status.enabled &&
              status.next_production &&
              ` · produksi berikutnya ${when(status.next_production)}`}
            {' · '}
            <Link to="/settings">atur</Link>
          </p>
          <p className="small muted">
            Pool {status.pool.length}/{status.pool_size}
            {status.free_slots.length > 0 &&
              ` · slot kosong: ${status.free_slots.slice(0, 3).map(when).join(', ')}`}
          </p>
          {status.pool.length > 0 && (
            <ol className="list">
              {status.pool.map((item) => (
                <li key={item.project_id} className="row">
                  <Link to={`/projects/${item.project_id}`}>{item.name}</Link>
                  <span className={`small job-${item.state}`}>{POOL_STATE[item.state]}</span>
                </li>
              ))}
            </ol>
          )}
        </>
      )}
      {message && <p role="status">{message}</p>}
    </section>
  )
}
