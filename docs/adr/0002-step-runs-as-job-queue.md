# 0002. Tabel step_runs sebagai job queue (tanpa Huey)

- Status: diterima, menggantikan bagian "Huey" di ADR 0001
- Tanggal: 2026-11-21

## Konteks

Run dari web harus berjalan di background, satu per satu, dan tetap ada setelah server restart. ADR 0001 memilih Huey (`SqliteHuey`). Saat diintegrasikan:

- `Consumer.start()` memasang signal handler sendiri, sehingga mengambil alih Ctrl+C dari uvicorn bila dijalankan di dalam `reelcraft serve`.
- Status tiap step sudah disimpan durable di `step_runs`. Huey akan menjadi antrean kedua yang harus dijaga tetap sinkron dengan yang pertama.

## Keputusan

- `step_runs` adalah antreannya. `claim(queue=True)` menandai step `queued` (dengan `queued_at` untuk urutan FIFO); satu thread worker di `serve` mengambil project yang paling lama menunggu.
- Run dari CLI memakai status `reserved`: tetap memblokir run lain di project yang sama, tetapi tidak pernah diambil worker.
- Saat server start, step yang tertinggal `running` ditandai gagal dan step yang menunggu di belakangnya dilepas; antrean project lain tetap berjalan.
- Progress ke web lewat SSE yang membaca `step_runs`, sehingga run dari CLI pun terlihat live.

## Konsekuensi

- Tidak ada dependency antrean; satu sumber kebenaran untuk status.
- Belum ada penjadwalan periodik. Dievaluasi ulang di v0.9 (Autopilot): Huey, APScheduler, atau loop sederhana.
