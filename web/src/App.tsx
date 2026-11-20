import { useEffect, useState } from 'react'
import { api } from './api/client'
import { Projects } from './Projects'

export default function App() {
  const [version, setVersion] = useState<string>()

  useEffect(() => {
    api.GET('/api/v1/version').then(({ data }) => setVersion(data?.version))
  }, [])

  return (
    <main>
      <header>
        <h1>Reelcraft</h1>
        {version && <span className="muted">v{version}</span>}
      </header>
      <Projects />
    </main>
  )
}
