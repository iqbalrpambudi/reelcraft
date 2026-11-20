import { useEffect, useState } from 'react'
import { Link, Route, Routes } from 'react-router'
import { api } from './api/client'
import { ProjectPage } from './ProjectPage'
import { Projects } from './Projects'
import { SettingsPage } from './SettingsPage'

export default function App() {
  const [version, setVersion] = useState<string>()

  useEffect(() => {
    api.GET('/api/v1/version').then(({ data }) => setVersion(data?.version))
  }, [])

  return (
    <main>
      <header>
        <Link to="/" className="brand">
          Reelcraft
        </Link>
        {version && <span className="muted small">v{version}</span>}
        <nav>
          <Link to="/settings">Settings</Link>
        </nav>
      </header>
      <Routes>
        <Route path="/" element={<Projects />} />
        <Route path="/projects/:id" element={<ProjectPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<p>Halaman tidak ditemukan.</p>} />
      </Routes>
    </main>
  )
}
