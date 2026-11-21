// Shown in the UI for the pipeline's step and status names
export const STEP_LABEL: Record<string, string> = {
  ingest: 'Ambil media',
  analyze: 'Analisis scene',
  tag: 'Deskripsi AI',
  script: 'Naskah',
  voice: 'Suara',
  edit: 'Susun klip',
  preview: 'Pratinjau',
  render: 'Render',
}
export const STATUS_LABEL: Record<string, string> = {
  pending: 'belum',
  reserved: 'disiapkan',
  queued: 'antre',
  running: 'berjalan',
  done: 'selesai',
  failed: 'gagal',
  cancelled: 'dibatalkan',
}
