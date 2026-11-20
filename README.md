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

Dashboard terbuka di http://127.0.0.1:8765.

## Development

```bash
make dev-api        # terminal 1: API dengan auto-reload
make dev-web        # terminal 2: Vite di http://localhost:5173 (proxy /api ke dev-api)
make test
make lint
```

## Struktur

```
src/reelcraft/
├─ core/     domain & config; tidak boleh import cli/api
├─ api/      FastAPI (router tipis) + serve web build
└─ cli.py    Typer
web/         dashboard React + Vite
docs/adr/    catatan keputusan arsitektur
```

Arah dependensi `cli → api → core` dijaga oleh `lint-imports` di CI.

Lihat [CONTRIBUTING.md](CONTRIBUTING.md) untuk branching, commit, dan rilis.
