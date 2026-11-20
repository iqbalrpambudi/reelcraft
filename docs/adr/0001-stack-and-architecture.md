# 0001. Stack dan arsitektur

- Status: diterima
- Tanggal: 2026-11-20

## Konteks

Reelcraft menulis ulang cliper-pro dengan fondasi yang lebih rapi. Masalah di cliper-pro yang ingin dihindari: skema DB lewat `create_all` + `ALTER` manual, orkestrasi yang memanggil endpoint HTTP sendiri, antrean job buatan sendiri yang hilang saat restart, type frontend yang ditulis ulang manual, dan modul raksasa.

## Keputusan

- **Satu package Python** (`reelcraft`), dua pintu masuk: CLI (Typer) dan API (FastAPI) yang juga menyajikan dashboard web. Keduanya memanggil lapisan yang sama.
- **Layering** `cli → api → core`, dijaga `import-linter`. Lapisan berikutnya (`pipeline`, `adapters`, `media`, `storage`) ditambahkan saat dibutuhkan dan didaftarkan di kontrak yang sama.
- **Pipeline per segment** (ingest, analyze, script, voice, edit, render, publish): tiap step punya input/output typed dan artifact di disk, bisa dijalankan ulang dari step mana pun, dari CLI maupun web.
- **Library**: SQLite + SQLAlchemy 2 + Alembic (migrasi saja, tanpa `create_all`), Huey (`SqliteHuey`) untuk job & jadwal, pydantic-ai untuk output LLM yang typed, PyAV + ffmpeg, PySceneDetect, faster-whisper, pysubs2, yt-dlp, Authlib + httpx.
- **Web**: React + Vite + TypeScript; type API di-generate dari OpenAPI.
- **Lifecycle**: trunk-based, squash merge, Conventional Commits, release-please.

## Konsekuensi

- Logika inti bisa dites tanpa HTTP, dan CLI tidak perlu server berjalan.
- Versi hanya di `src/reelcraft/__init__.py`, sehingga `uv.lock` tidak basi tiap rilis.
- Butuh repo GitHub agar CI dan rilis otomatis berjalan.
