# Roadmap

Milestone sampai 1.0. Rilis ditahan sampai 1.0 (lihat CONTRIBUTING, "Fase awal"); versi di sini adalah nama milestone, bukan tag. Centang tugas di commit yang menyelesaikannya.

Pipeline per project: **Ingest → Analyze → Script → Voice → Edit → Render → Publish**.

## v0.1 Skeleton ✅
- [x] uv + hatch, Typer CLI, FastAPI, dashboard Vite + React
- [x] ruff, basedpyright, import-linter, pre-commit, Conventional Commits
- [x] CI dan release-please

## v0.2 Project ✅
- [x] SQLite + SQLAlchemy + Alembic (migrasi otomatis saat start)
- [x] CRUD project: service, API, CLI (`reelcraft project`), web
- [x] Type web di-generate dari OpenAPI; lint cek migrasi & type

## v0.3 Pipeline engine, Ingest, Analyze ✅
- [x] Kontrak step + runner: status per step di DB, jalankan rentang step, step hilir di-reset saat step hulu diulang, cegah run ganda per project, batal kooperatif
- [x] CLI `reelcraft run <project> [--from] [--to]` dan `reelcraft status <project>` dengan progress
- [x] Media: tambah dari file lokal / URL lewat CLI (`reelcraft media`)
- [x] Media dari web: upload file / URL / path lokal
- [x] Step Ingest: salin file atau unduh via yt-dlp (sampai 1080p, solver JS bawaan), probe metadata (ffprobe)
- [x] Step Analyze: deteksi scene (PySceneDetect) + thumbnail per scene
- [x] Job queue untuk run dari web: `step_runs` sebagai antrean, worker di dalam `reelcraft serve` (ADR 0002)
- [x] Progress live ke web via SSE; tombol batal
- [x] Web: routing, halaman detail project dengan stepper segment, daftar media & scene
- [x] `reelcraft doctor`: cek ffmpeg, data dir, versi

## v0.4 Settings & AI ✅
- [x] Settings di DB, secret terenkripsi (Fernet, key di data dir)
- [x] Adapter LLM via pydantic-ai: Gemini & OpenAI-compatible, pilih model per tugas
- [x] Vision tagging scene (step `tag` setelah Analyze), retry 5xx dengan backoff, run ulang hanya untuk scene yang gagal
- [x] Halaman Settings di web, `reelcraft config` di CLI

## v0.5 Script & Voice
- [ ] Template narasi (preset + kustom)
- [ ] Step Script: naskah terstruktur dari LLM berdasarkan topik + scene
- [ ] Edit naskah di web dan CLI (`$EDITOR`)
- [ ] Adapter TTS: Gemini, ElevenLabs
- [ ] Step Voice: audio narasi + timestamp per kata (faster-whisper)

## v0.6 Edit & Render
- [ ] Step Edit: auto-match scene ke segmen narasi (port `matching.py`)
- [ ] Subtitle karaoke ASS (pysubs2) + gaya subtitle
- [ ] Library BGM per mood + auto-duck
- [ ] Step Render: 9:16 via ffmpeg, background fill, watermark, render preview
- [ ] Web: pratinjau timeline & ubah urutan klip, pengaturan subtitle

## v0.7 Dashboard
- [ ] Workflow segment lengkap: buka tiap segment, lihat & edit artifact, "jalankan ulang dari sini"
- [ ] Player video/audio untuk hasil tiap step
- [ ] Indikator antrean global dan riwayat job

## v0.8 Discovery
- [ ] Pencarian footage multi-sumber: YouTube, Pexels, Pixabay, Archive.org
- [ ] Filter (durasi, lisensi, sudah diimpor) dan impor multi-klip

## v0.9 Publish & Autopilot
- [ ] Publish YouTube (OAuth + upload terjadwal)
- [ ] Publish Facebook Page Reels
- [ ] Autopilot: pool video, jadwal produksi & slot posting (pilih penjadwal, lihat ADR 0002)

## v0.10 QC
- [ ] Gate kualitas per step (port `qc.py`, dipecah per pemeriksaan)
- [ ] Auto-fix naskah & laporan QC di web

## v1.0 Siap pakai
- [ ] Mode service: start/stop di background, auto-start saat login (launchd / systemd)
- [ ] Logging terstruktur (structlog) + `reelcraft logs`
- [ ] Dokumentasi pengguna & installer
- [ ] Rilis pertama: push `main`, merge PR rilis

## Setelah 1.0 (ide)
- Generator video perbandingan peta (ukuran asli negara/pulau) sebagai alternatif step Ingest
