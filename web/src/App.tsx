import { useEffect, useState } from 'react'
import { Link, Route, Routes } from 'react-router'
import { api, useQueue } from './api/client'
import { JobsPage } from './JobsPage'
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
        <nav className="row">
          <QueueIndicator />
          <Link to="/settings">Settings</Link>
        </nav>
      </header>
      <Routes>
        <Route path="/" element={<Projects />} />
        <Route path="/projects/:id" element={<ProjectPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/jobs" element={<JobsPage />} />
        <Route path="*" element={<p>Halaman tidak ditemukan.</p>} />
      </Routes>
    </main>
  )
}

function QueueIndicator() {
  const queue = useQueue()
  const running = queue.filter((q) => q.status === 'running').length
  const waiting = queue.length - running
  return (
    <Link to="/jobs" className={running ? 'queue-busy' : 'muted'}>
      {queue.length === 0 ? 'Jobs' : `${running} berjalan · ${waiting} antre`}
    </Link>
  )
}
