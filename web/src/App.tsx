import { useEffect, useState } from 'react'

export default function App() {
  const [version, setVersion] = useState<string | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    fetch('/api/v1/version')
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((d: { version: string }) => setVersion(d.version))
      .catch(() => setError(true))
  }, [])

  return (
    <main>
      <h1>Reelcraft</h1>
      <p className="muted">A production line for short-form video.</p>
      <p role="status">
        {error ? 'API tidak terjangkau' : version ? `v${version}` : 'Memuat...'}
      </p>
    </main>
  )
}
