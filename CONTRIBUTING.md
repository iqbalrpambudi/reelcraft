# Contributing

## Branching (trunk-based)

| Branch | Isi |
|---|---|
| `main` | Selalu bisa dirilis. Tidak boleh commit langsung; semua lewat PR. |
| `feat/<nama>` | Fitur baru |
| `fix/<nama>` | Bug fix |
| `refactor/`, `perf/`, `docs/`, `chore/`, `ci/`, `test/` `<nama>` | Non-fitur |

- `<nama>` kebab-case pendek, mis. `feat/pipeline-runner`, `fix/tts-retry`.
- Satu branch untuk satu perubahan. Umurnya pendek (idealnya < 3 hari); pecah fitur besar jadi beberapa PR.
- Merge ke `main` pakai **squash merge**. Judul PR menjadi pesan commit di `main`, jadi judul PR wajib Conventional Commits (dicek CI).
- Hapus branch setelah merge. Jangan force push ke `main`.

```bash
git switch main && git pull
git switch -c feat/<nama>
# ... kerja + commit ...
make lint && make test
git push -u origin feat/<nama>   # buka PR ke main, judul: feat(scope): ...
```

## Commit

Format [Conventional Commits](https://www.conventionalcommits.org/), dicek hook `commit-msg`:

```
<type>(<scope>): <ringkasan, huruf kecil, tanpa titik>
```

- `type`: `feat`, `fix`, `perf`, `refactor`, `docs`, `test`, `chore`, `ci`, `build`, `style`.
- `scope`: nama modul, mis. `cli`, `api`, `core`, `pipeline`, `web`, `publish/youtube`.
- Breaking change: `feat(api)!: ...` atau footer `BREAKING CHANGE: ...`.

## Versioning

[SemVer](https://semver.org/). Satu sumber versi: `src/reelcraft/__init__.py`, **jangan diubah manual**.

| Commit sejak rilis terakhir | Sebelum 1.0.0 | Sejak 1.0.0 |
|---|---|---|
| `feat!` / `BREAKING CHANGE` | minor | major |
| `feat` | minor | minor |
| `fix`, `perf` | patch | patch |
| lainnya | tidak rilis | tidak rilis |

## Rilis (otomatis, release-please)

1. Setiap push ke `main`, release-please membuka/memperbarui **PR rilis** berisi bump versi + `CHANGELOG.md`.
2. Merge PR rilis itu kapan pun siap rilis.
3. Workflow membuat tag `vX.Y.Z` + GitHub Release, lalu mengunggah wheel (dashboard web sudah di dalamnya).

Hotfix: branch `fix/<nama>` dari `main` seperti biasa; rilis patch keluar lewat PR rilis berikutnya.

## Checklist PR

- [ ] `make lint` dan `make test` lulus
- [ ] Logika baru punya test
- [ ] Perubahan skema DB disertai migrasi Alembic
- [ ] Keputusan arsitektur baru dicatat di `docs/adr/`
