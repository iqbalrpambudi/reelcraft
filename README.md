# Reelcraft

A production line for short-form video (Shorts, Reels), from the CLI or a web dashboard.

## Prasyarat

- [uv](https://docs.astral.sh/uv/) (Python 3.12 diunduh otomatis)
- Node.js 24+
- ffmpeg (dibutuhkan mulai pipeline render)

## Mulai

```bash
make setup          # deps Python + web, pasang git hooks
make web-build      # build dashboard ke dalam package
uv run reelcraft serve
```

Dashboard terbuka di http://127.0.0.1:8765. Data disimpan di `~/.reelcraft` (ubah dengan `REELCRAFT_DATA_DIR`).

## CLI

```bash
reelcraft project new "Jawa di Eropa"
reelcraft project list
reelcraft project show 6c75          # id boleh awalan yang unik
reelcraft project rename 6c75 "Nama baru"
reelcraft project delete 6c75 -y

reelcraft media add 6c75 ~/Videos/klip.mp4 https://youtu.be/...
reelcraft run 6c75                   # lanjut dari step yang belum selesai
reelcraft run 6c75 --from analyze    # ulang dari step tertentu (step setelahnya ikut di-reset)
reelcraft status 6c75
reelcraft doctor                     # cek ffmpeg, data dir, dashboard
```

Pipeline per project: `ingest` (salin/unduh media, baca metadata) → `analyze` (deteksi scene + thumbnail) → step berikutnya menyusul (lihat [docs/ROADMAP.md](docs/ROADMAP.md)).

## Development

```bash
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
├─ storage/    model SQLAlchemy, session, migrasi Alembic
└─ core/       config & error; tidak import apa pun dari layer lain
web/           dashboard React + Vite; src/api/schema.d.ts di-generate
docs/adr/      catatan keputusan arsitektur
```

Arah dependensi `cli → api → services → storage → core` dijaga oleh `lint-imports`. Skema DB hanya berubah lewat migrasi; aplikasi otomatis migrate saat start.

Lihat [CONTRIBUTING.md](CONTRIBUTING.md) untuk branching, commit, dan rilis.
