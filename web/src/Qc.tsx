import { useEffect, useState } from 'react'
import { api, errorMessage, type QcReport } from './api/client'

const SEVERITY_LABEL: Record<string, string> = {
  blocker: 'penghalang',
  major: 'penting',
  minor: 'saran',
}

/** The step's last quality report, with a recheck and, for the script, an auto-fix. */
export function QcPanel({
  projectId,
  step,
  disabled,
  onFixed,
}: {
  projectId: string
  step: string
  disabled: boolean
  onFixed: () => void
}) {
  const [report, setReport] = useState<QcReport | null>()
  const [status, setStatus] = useState('')
  const path = { project_id: projectId }

  useEffect(() => {
    api
      .GET('/api/v1/projects/{project_id}/qc', { params: { path: { project_id: projectId } } })
      .then(({ data }) => setReport(data?.[step] ?? null))
  }, [projectId, step])

  const recheck = async () => {
    const { data, error } = await api.POST('/api/v1/projects/{project_id}/qc/{step}', {
      params: { path: { ...path, step } },
    })
    if (error) return setStatus(errorMessage(error))
    setReport(data)
    setStatus('')
  }

  const fix = async () => {
    const { data, error } = await api.POST('/api/v1/projects/{project_id}/script/fix', {
      params: { path },
    })
    if (error) return setStatus(errorMessage(error))
    setReport(data)
    setStatus(
      data.fixes.length ? `Diperbaiki: ${data.fixes.join('; ')}.` : 'Tidak ada yang diubah.',
    )
    onFixed()
  }

  if (report === undefined) return null
  const fixable = report?.issues.some((i) => i.fixable)

  return (
    <section aria-labelledby={`qc-${step}`} className="qc">
      <div className="row">
        <h3 id={`qc-${step}`}>QC</h3>
        <div className="row">
          {step === 'script' && fixable && (
            <button type="button" className="quiet small" onClick={fix} disabled={disabled}>
              Perbaiki otomatis
            </button>
          )}
          <button type="button" className="quiet small" onClick={recheck} disabled={disabled}>
            Cek ulang
          </button>
        </div>
      </div>
      {!report ? (
        <p className="muted small">Belum dicek. QC jalan otomatis setelah step ini selesai.</p>
      ) : report.issues.length === 0 ? (
        <p className="small job-done">Lolos, tidak ada catatan.</p>
      ) : (
        <ul className="list">
          {report.issues.map((i, n) => (
            <li key={n} className="small">
              <span className={`qc-${i.severity}`}>{SEVERITY_LABEL[i.severity]}</span> {i.message}
            </li>
          ))}
        </ul>
      )}
      {report && report.fixes.length > 0 && !status && (
        <p className="small muted">Diperbaiki otomatis: {report.fixes.join('; ')}.</p>
      )}
      {status && (
        <p role="status" className="small">
          {status}
        </p>
      )}
    </section>
  )
}
