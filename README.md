# Reelcraft

A production line for short-form video (Shorts, Reels), from the CLI or a web dashboard.

Footage → naskah AI → suara → klip yang dicocokkan dengan narasi → render 1080×1920 dengan subtitle karaoke dan musik → posting ke YouTube / Facebook Page, manual atau oleh Autopilot. QC mengecek tiap tahap.

## Pasang

macOS / Linux:

```bash
curl -LsSf https://raw.githubusercontent.com/iqbalrpambudi/reelcraft/main/install.sh | sh
reelcraft serve          # atau: reelcraft service install
```

Panduan lengkap (API key, membuat video, posting, Autopilot, CLI, masalah umum): **[docs/PANDUAN.md](docs/PANDUAN.md)**.

## Development

Prasyarat: [uv](https://docs.astral.sh/uv/), Node.js 24+, ffmpeg.

```bash
make setup          # deps Python + web, pasang git hooks
make web-build      # build dashboard ke dalam package
uv run reelcraft serve

make dev-api        # terminal 1: API dengan auto-reload
make dev-web        # terminal 2: Vite di http://localhost:5173 (proxy /api ke dev-api)
make test
make lint                   # termasuk cek migrasi vs model dan type web vs API
make migration m="add scenes"   # setelah mengubah model di storage/models.py
make api-types              # setelah mengubah endpoint / schema API
```

## Struktur

```
src/reelcraft/
├─ cli/        Typer; satu file per kelompok perintah
├─ api/        FastAPI, router tipis + serve web build
├─ services/   use case yang dipakai bersama CLI & API
├─ pipeline/   runner, antrean, step (ingest → render), matching, gate QC
├─ ai/         model pydantic-ai dari Settings, prompt & output terstruktur, TTS
├─ publish/    klien YouTube & Facebook (OAuth, upload)
├─ media/      ffmpeg, scene detection, yt-dlp, whisper, subtitle, pencarian footage
├─ storage/    model SQLAlchemy, session, migrasi Alembic
└─ core/       config, error, enkripsi secret, logging; tidak import apa pun dari layer lain
web/           dashboard React + Vite; src/api/schema.d.ts di-generate
docs/adr/      catatan keputusan arsitektur
```

Arah dependensi `cli → api → services → pipeline → ai | publish → storage | media → core` dijaga oleh `lint-imports`. Skema DB hanya berubah lewat migrasi; aplikasi otomatis migrate saat start.

Lihat [CONTRIBUTING.md](CONTRIBUTING.md) untuk branching, commit, dan rilis.
