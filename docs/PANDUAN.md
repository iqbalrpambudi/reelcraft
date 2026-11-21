# Panduan Reelcraft

Reelcraft membuat video pendek vertikal (YouTube Shorts, Facebook Reels) dari footage: cari atau tambah video sumber, AI menulis naskah dan membacakannya, scene dicocokkan dengan narasi, lalu video dirender lengkap dengan subtitle karaoke dan musik. Hasilnya bisa langsung diposting, atau biarkan Autopilot membuat dan menjadwalkan video sendiri.

Semua berjalan di komputer Anda. Yang keluar ke internet hanya panggilan ke AI (Gemini atau OpenAI-compatible), pencarian footage, dan upload ke platform.

## 1. Pasang

macOS atau Linux (Windows: pakai WSL):

```bash
curl -LsSf https://raw.githubusercontent.com/iqbalrpambudi/reelcraft/main/install.sh | sh
```

Installer memasang [uv](https://docs.astral.sh/uv/) dan ffmpeg bila belum ada, lalu Reelcraft dari rilis terbaru, dan menutup dengan `reelcraft doctor`. Tambahkan `-s -- --service` di akhir perintah agar Reelcraft langsung menyala di background dan ikut menyala setiap login.

Versi tertentu: `REELCRAFT_VERSION=v1.0.0` sebelum `sh`. Memperbarui: jalankan perintah yang sama lagi. Menghapus: `reelcraft service uninstall` (bila dipasang) lalu `uv tool uninstall reelcraft`. Data Anda tetap di `~/.reelcraft` sampai folder itu dihapus.

## 2. Jalankan

```bash
reelcraft serve                 # dashboard terbuka di http://127.0.0.1:8765
```

Atau sebagai service di background:

```bash
reelcraft service install       # menyala sekarang dan setiap login
reelcraft service status
reelcraft service stop | start
reelcraft service uninstall
```

Service menyimpan PATH dan folder saat `install` dijalankan; jalankan ulang `install` bila ffmpeg pindah atau Anda memakai `.env` di folder lain.

## 3. Isi API key

Buka **Settings** di dashboard (atau `reelcraft config set <nama>`):

| Setting | Untuk | Dapatkan di |
|---|---|---|
| Gemini API key | naskah, deskripsi scene, suara (TTS) | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| Pexels / Pixabay API key | cari footage berlisensi bebas (opsional) | pexels.com/api, pixabay.com/api/docs |

Klik **Uji koneksi AI** untuk memastikan key dan model bekerja. API key disimpan terenkripsi di database lokal. Model bisa diganti: `provider:model` dengan provider `google`, atau `openai` untuk layanan OpenAI-compatible (OpenRouter, Ollama, LM Studio lewat *base URL*).

Bila model teks sering lambat atau tidak menjawab, ganti ke `google:gemini-flash-lite-latest`. Setiap panggilan AI dibatasi 120 detik lalu dicoba ulang beberapa kali.

## 4. Membuat video

1. **Buat project** di halaman depan.
2. **Ambil media**: tempel URL video (YouTube, dll.), path file, atau unggah. Atau pakai **Cari footage**: satu pencarian ke YouTube, Pexels, Pixabay, dan Archive.org, dengan filter durasi dan *lisensi bebas* (public domain, CC BY, CC BY-SA: boleh diedit dan dimonetisasi). Centang beberapa hasil lalu **Impor**.
3. **Naskah**: isi *topik*, pilih *template* gaya narasi (fakta, cerita, listicle, edukasi, bebas), tambahkan instruksi bila perlu, dan pilih musik latar.
4. Klik **Jalankan**. Pipeline berjalan berurutan dan progresnya tampil live:

| Step | Isi |
|---|---|
| Ambil media | unduh/salin footage, baca metadata |
| Analisis scene | potong per scene + thumbnail |
| Deskripsi AI | model vision mendeskripsikan tiap scene |
| Naskah | AI menulis narasi dari topik dan scene |
| Suara | TTS Gemini + timestamp per kata (faster-whisper) |
| Susun klip | scene dicocokkan dengan kalimat narasi |
| Pratinjau | render cepat setengah ukuran |
| Render | 1080×1920, subtitle karaoke, musik yang mengecil saat narasi |

Klik kartu step untuk melihat dan mengubah hasilnya: edit naskah, putar suara per kalimat, ubah urutan klip, putar pratinjau. **Jalankan ulang dari sini** mengulang step itu dan semua sesudahnya. **Pratinjau** menjalankan sampai pratinjau saja, untuk mengecek potongan sebelum render penuh.

Musik latar: taruh file audio di `~/.reelcraft/music/<mood>/`, misalnya `~/.reelcraft/music/santai/lagu.mp3`. Setiap folder menjadi satu pilihan mood. Tampilan subtitle, background (blur, cover, atau warna), watermark, dan model whisper diatur di Settings.

### QC (kontrol kualitas)

Setelah Naskah, Suara, Susun klip, dan Render, hasilnya dicek otomatis. Catatan tampil di bawah tiap step:

- **penghalang**: step dianggap gagal (mis. naskah kosong, file render rusak).
- **penting / saran**: video tetap jadi; Anda yang memutuskan (hook terlalu panjang, klip terlalu singkat, footage buram, durasi lewat 90 detik, dll.).

Naskah dari AI otomatis dirapikan: label seperti `Narator:` atau `[MUSIK]` dihapus, kalimat yang terlalu panjang dipecah, yang terlalu pendek digabung. Untuk naskah yang Anda tulis sendiri, klik **Perbaiki otomatis** (atau `reelcraft qc <project> --fix`).

## 5. Posting

Hubungkan akun di **Settings → Akun posting**. Keduanya butuh aplikasi developer milik Anda sendiri (gratis). *Redirect URI* yang harus didaftarkan ditampilkan di halaman itu; harus sama persis dengan alamat yang Anda pakai membuka dashboard (`127.0.0.1` dan `localhost` dianggap berbeda).

**YouTube**
1. [console.cloud.google.com](https://console.cloud.google.com): buat project, aktifkan **YouTube Data API v3**.
2. *OAuth consent screen*: tipe External, tambahkan email Anda sebagai *test user*.
3. *Credentials → Create OAuth client ID*: tipe **Web application**, isi *Authorized redirect URI*.
4. Salin client ID dan secret ke Settings, lalu klik **Hubungkan** di YouTube.

Selama aplikasi berstatus *Testing*, Google mencabut izin setelah 7 hari: hubungkan ulang, atau ubah status ke *In production*. Video yang diunggah lewat project API yang belum lolos audit YouTube dikunci *private* oleh YouTube; ajukan audit di Google bila ingin video publik.

**Facebook Page**
1. [developers.facebook.com](https://developers.facebook.com): buat app tipe Business, tambahkan produk **Facebook Login**.
2. Di *Valid OAuth Redirect URIs*, isi redirect URI dari Settings.
3. Salin App ID dan App secret ke Settings, klik **Hubungkan**, dan pilih **satu** Page tujuan saat login.

Lalu buka step **Render**, isi judul dan deskripsi, pilih platform, dan **Unggah sekarang** atau isi waktu tayang lalu **Jadwalkan**. Video diunggah segera; bila dijadwalkan, platform yang menayangkannya pada waktu itu, jadi komputer tidak perlu menyala tepat pada jam tayang. Semua posting terlihat di halaman **Jobs**. Yang gagal bisa diulang.

## 6. Autopilot

Autopilot membuat video sendiri dan mengisi jadwal posting. Atur di Settings:

| Setting | Contoh | Arti |
|---|---|---|
| Autopilot | `on` | nyalakan |
| Niche | Fakta unik seputar kerajinan... | tema channel; AI memilih ide di dalamnya |
| Jam produksi | `12:00,18:00` | tiap jam ini satu video baru mulai dibuat |
| Slot posting | `07:00,17:00` | jam tayang harian |
| Platform | `youtube,facebook` | akun harus sudah terhubung |
| Ukuran pool | `4` | produksi berhenti bila 4 video jadi belum terjadwal |

Pada jam produksi, AI mengusulkan ide (judul, topik, kata kunci), footage dicari (berlisensi bebas didahulukan), lalu pipeline penuh berjalan. Video yang selesai mengisi slot kosong terdekat di setiap platform. Status, pool, dan slot kosong tampil di halaman **Jobs**; **Buat video sekarang** membuat satu tanpa menunggu jam produksi. Autopilot hanya berjalan selama `reelcraft serve` atau service menyala.

Tanpa key Pexels/Pixabay, footage Autopilot banyak berasal dari YouTube milik orang lain dan bisa membawa watermark atau klaim hak cipta. Isi key Pexels/Pixabay, dan periksa video di pool sebelum slotnya tiba.

## 7. CLI

Semua yang ada di dashboard juga ada di terminal. Id project boleh ditulis awalannya saja.

```bash
reelcraft project new "Pabrik korek api"
reelcraft project brief 6c75 --topic "Cara korek api dibuat" --template fakta --music santai
reelcraft media find 6c75 "match factory" --free        # cari footage
reelcraft media find 6c75 "match factory" --add 1 --add 3
reelcraft media add 6c75 ~/Videos/klip.mp4 https://youtu.be/...
reelcraft run 6c75                     # lanjut dari step yang belum selesai
reelcraft run 6c75 --from voice        # ulang dari step tertentu
reelcraft script 6c75                  # edit naskah di $EDITOR
reelcraft qc 6c75 --fix
reelcraft publish 6c75 --to youtube --to facebook --at "2026-12-01 07:00"
reelcraft posts
reelcraft autopilot [--now]
reelcraft jobs                         # antrean dan riwayat run
reelcraft logs -f --level warning      # log server dan CLI
reelcraft config list | set | unset | check
reelcraft doctor
```

`reelcraft <perintah> --help` menjelaskan semua opsinya.

## 8. Bila ada masalah

- **`reelcraft doctor`** mengecek ffmpeg, folder data, dan dashboard.
- **`reelcraft logs --level warning`** menampilkan step yang gagal, upload yang gagal, dan error lain beserta penyebabnya. Log ada di `~/.reelcraft/logs/`.
- Step gagal: buka step itu di dashboard. Pesan error tampil di sana; perbaiki lalu **Jalankan ulang dari sini**.
- "AI tidak bisa dihubungi" atau sering timeout: layanan AI sedang sibuk. Coba lagi nanti atau ganti ke model lite.
- Upload "terhenti saat mengunggah": server mati di tengah upload. Cek di YouTube/Facebook apakah videonya sudah ada sebelum menekan **Ulangi**, agar tidak dobel.
- Data (database, footage, hasil render) ada di `~/.reelcraft`. Pindahkan dengan `REELCRAFT_DATA_DIR`; port dan alamat dengan `REELCRAFT_PORT` dan `REELCRAFT_HOST`.
