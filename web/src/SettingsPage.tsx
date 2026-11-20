import { useEffect, useState } from 'react'
import { api, errorMessage, type AICheck, type SettingItem } from './api/client'

const SOURCE_LABEL: Record<string, string> = {
  db: 'tersimpan',
  env: 'dari environment / .env',
  default: 'bawaan',
  unset: 'belum diatur',
}

export function SettingsPage() {
  const [items, setItems] = useState<SettingItem[]>()
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [status, setStatus] = useState('')
  const [checks, setChecks] = useState<AICheck[]>()
  const [checking, setChecking] = useState(false)

  useEffect(() => {
    api.GET('/api/v1/settings').then(({ data }) => setItems(data))
  }, [])

  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    const { data, error } = await api.PATCH('/api/v1/settings', { body: draft })
    if (error) return setStatus(errorMessage(error))
    setItems(data)
    setDraft({})
    setStatus('Tersimpan.')
  }

  const reset = async (key: string) => {
    const { data, error } = await api.PATCH('/api/v1/settings', { body: { [key]: null } })
    if (error) return setStatus(errorMessage(error))
    setItems(data)
    setStatus('Dikembalikan ke nilai environment / bawaan.')
  }

  const check = async () => {
    setChecking(true)
    setChecks(undefined)
    const { data, error } = await api.POST('/api/v1/settings/check-ai')
    setChecking(false)
    if (error) return setStatus(errorMessage(error))
    setChecks(data)
  }

  if (!items) return <p className="muted">Memuat...</p>

  return (
    <>
      <h1>Settings</h1>
      <form onSubmit={save} className="settings">
        {items.map((it) => (
          <div key={it.key} className="field">
            <label htmlFor={`setting-${it.key}`}>{it.label}</label>
            <input
              id={`setting-${it.key}`}
              type={it.secret ? 'password' : 'text'}
              autoComplete="off"
              placeholder={it.value ?? it.default ?? ''}
              value={draft[it.key] ?? (it.secret ? '' : it.source === 'db' ? (it.value ?? '') : '')}
              onChange={(e) => setDraft({ ...draft, [it.key]: e.target.value })}
            />
            <div className="row small muted">
              <span>
                {SOURCE_LABEL[it.source]}
                {it.help && ` · ${it.help}`}
              </span>
              {it.source === 'db' && (
                <button type="button" className="quiet small" onClick={() => reset(it.key)}>
                  Reset
                </button>
              )}
            </div>
          </div>
        ))}
        <div className="row">
          <button type="submit" disabled={Object.keys(draft).length === 0}>
            Simpan
          </button>
          <button type="button" className="quiet" onClick={check} disabled={checking}>
            {checking ? 'Menguji...' : 'Uji koneksi AI'}
          </button>
        </div>
        {status && <p role="status">{status}</p>}
      </form>
      {checks && (
        <ul className="list" aria-label="Hasil uji koneksi">
          {checks.map((c) => (
            <li key={c.task}>
              <strong className={c.ok ? '' : 'error'}>{c.ok ? 'OK' : 'Gagal'}</strong> · {c.task} ·{' '}
              <code>{c.model}</code>
              <div className="muted small">{c.message}</div>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}
