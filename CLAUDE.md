# Reelcraft

@CONTRIBUTING.md

- Fase awal: kerja lokal, squash merge lokal ke `main`, jangan push dan jangan rilis kecuali diminta.
- Jangan commit langsung ke `main`; buat branch dulu sesuai tabel di atas.
- Kode domain di `src/reelcraft/core` tidak boleh import `reelcraft.cli` / `reelcraft.api`.
- `make lint && make test` harus lulus sebelum push.
