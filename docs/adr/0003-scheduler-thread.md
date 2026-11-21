# 0003. Scheduler: satu thread loop di `serve` (tanpa Huey / APScheduler)

- Status: diterima
- Tanggal: 2026-11-21

## Konteks

v0.9 butuh kerja berkala: mengunggah post yang antre dan, untuk Autopilot, memulai produksi pada jam tertentu lalu mengisi slot posting. ADR 0002 menunda pilihan antara Huey, APScheduler, atau loop sederhana.

## Keputusan

- Satu thread `scheduler` di `serve`, di samping worker pipeline, yang menjalankan `tick()` tiap beberapa detik.
- Semua jadwal diturunkan dari data yang sudah ada (tabel `posts`, `projects`, setting Autopilot), bukan disimpan di antrean terpisah. Restart tidak kehilangan apa pun: tick berikutnya menghitung ulang.
- Jadwal tayang diserahkan ke platform (`publishAt` YouTube, `scheduled_publish_time` Facebook). Video diunggah segera, sehingga komputer tidak perlu menyala tepat pada jam tayang.
- Klaim post memakai `UPDATE ... WHERE status = 'queued'`, sehingga `reelcraft publish` di CLI dan server tidak mengunggah dua kali.
- Upload yang terputus karena restart ditandai gagal, bukan diulang otomatis, agar tidak ada video ganda.

## Konsekuensi

- Tanpa dependency baru; jadwal hanya berjalan selama `reelcraft serve` hidup (mode service di v1.0 menjawab ini).
- Ketepatan waktu sebatas interval tick (detik), cukup untuk jadwal per jam.
