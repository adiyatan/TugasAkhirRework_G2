# Requirement Modul Input Mutasi Bank

Dokumen ini menjadi acuan kerja pembagian tugas **Backend** dan **Frontend** untuk menu **Input Mutasi Bank** (`input_mutasi`) pada sistem keuangan **PT Lokal Komoditi Indonesia**, selaras dengan skema SQLite di [database.py](../backend/app/core/database.py).

---

## 1. Tujuan & Hak Akses (RBAC)
1. Mengekstrak dokumen rekening koran bank (format `.pdf`) menjadi baris mutasi terstandarisasi di tabel `mutasi_bank` sehingga siap dicocokkan (*matching*) dengan data `transaksi_internal` dari Input Struk.
2. **Hak Akses Menu** (`require_menu("input_mutasi")`):
   - Hanya role `finance` dan `management` yang dapat mengunggah, melihat daftar batch/baris mutasi, dan menghapus batch mutasi.
   - Role `staff` **wajib ditolak** (`403 Forbidden`) pada seluruh endpoint mutasi.

---

## 2. Sumber Data & Jenis Bank yang Didukung
Sistem membaca daftar rekening non-tunai (`is_cash = 0`) dari tabel `rekening_perusahaan`:
1. **PDF Berbasis Teks (contoh: BRI IBBIZ)**
   - Diparsing secara deterministik (tanpa biaya AI) untuk membaca tanggal, waktu, uraian (membersihkan kode trailing teller/user ID bila ada), kolom Debet/Kredit, dan saldo berjalan.
2. **PDF Kurva Vektor / Scan Gambar (contoh: BNI Wondr, Bank Jago, BRI Operasional)**
   - Setiap halaman PDF dirender menjadi gambar resolusi cukup, lalu diekstrak menjadi daftar baris transaksi terstruktur menggunakan Vision AI.
3. **Mode Pemilihan Bank**
   - User dapat memilih target rekening dari `rekening_perusahaan` (`is_cash = 0`) atau mode `Auto` (sistem mendeteksi nomor rekening dari isi PDF dan mencocokkannya ke `rekening_perusahaan.no_rekening`).
   - Akun `Kas Operasional` (`is_cash = 1`) **tidak** tersedia untuk upload mutasi PDF.

---

### 2.1 Kenapa Ada 2 Jalur & Cara Kerja Vision AI pada Mutasi PDF

Tidak semua PDF mutasi bank bisa dibaca dengan cara yang sama, karena struktur internal file PDF tiap bank berbeda:

| Jalur Ekstraksi | Contoh File Nyata | Kapan Dipakai | Kenapa Pakai Jalur Ini |
| :--- | :--- | :--- | :--- |
| **Jalur 1 — Deterministik (Teks PDF)** | `Mutasi Rekening BRI-Januari 2026.pdf` (BRI IBBIZ) | Saat `bank_choice` = `Auto` / `BRI` dan teks PDF terbaca terstruktur | Teks di PDF BRI IBBIZ utuh (format baris `DD/MM/YY HH:MM:SS ... Debet Kredit Saldo`), sehingga ekstraksi deterministik jauh lebih cepat, gratis (0 token AI), dan bebas risiko salah baca angka. |
| **Jalur 2 — Vision AI (Render Halaman → Gambar)** | `BNI_Mutasi_Januari_2026.pdf` (BNI Wondr), Bank Jago, BRI Operasional | Saat jalur teks tidak menemukan baris transaksi (PDF berbasis kurva vektor/grafis atau hasil scan) | PDF seperti BNI Wondr menyimpan huruf/angka sebagai **kurva vektor**, bukan teks biasa—ketika dibaca sebagai teks hasilnya kosong/berantakan. Solusinya tiap halaman PDF dirender menjadi gambar lalu dibaca oleh Vision AI. |

#### Alur & Contoh Penggunaan Vision AI untuk Mutasi (Per Halaman PDF)
1. **Render Halaman PDF menjadi Gambar**:
   - Dokumen PDF dibuka dan tiap halaman dirender menjadi gambar beresolusi tinggi (misal skala `2.0x`) agar angka kecil, tanda `+`/`-`, warna nominal, dan jam transaksi terbaca tajam.
2. **Input yang Dikirim ke Vision AI (Per Halaman)**:
   - Gambar 1 halaman mutasi + prompt terstruktur dengan `bank_hint` (misal `BNI`).
   - Prompt menginstruksikan AI untuk:
     - Mengabaikan baris *"Saldo Awal"*, *"Saldo Akhir"*, dan catatan footer non-transaksi.
     - Membaca nomor rekening di header halaman (`no_rekening`).
     - Membedakan arah mutasi berdasarkan tanda/warna/kolom: bertanda `+` / hijau / kolom Kredit → `tipe = "CR"`; bertanda `-` / hitam / kolom Debet → `tipe = "DB"`.
     - Menormalisasi `tanggal` (`YYYY-MM-DD`), `waktu` (`HH:MM:SS` tanpa `"WIB"`), `nominal` positif, dan `saldo`.
3. **Contoh Output JSON Vision AI (1 Halaman BNI Wondr)**:
   - AI mengembalikan JSON berisi `no_rekening` dan array `transaksi`, misalnya:
     - `no_rekening`: `"1783680837"`
     - `transaksi[0]`: `tanggal = "2026-01-01"`, `waktu = "16:28:32"`, `uraian = "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI"`, `tipe = "DB"`, `nominal = 800353`, `saldo = 1380359`.
4. **Pengaman Setelah Vision AI (Validasi Matematis di Backend)**:
   - Karena Vision AI tetap berpotensi melewatkan 1 baris di PDF multi-halaman, backend **wajib** menjalankan **Cek Konsistensi Saldo** (`saldo_awal_periode + total_CR - total_DB == saldo_akhir_periode`) dan menampilkannya pada Tahap Preview sebelum data disimpan ke `mutasi_bank`.

---

## 3. Aturan Normalisasi Baris Mutasi
Setiap baris mutasi yang dihasilkan sebelum disimpan ke `mutasi_bank` wajib memenuhi kontrak berikut:
1. **`rekening_id` & `no_rekening`**: Merujuk ke baris sah di `rekening_perusahaan`.
2. **`tanggal` & `waktu`**: Format baku `YYYY-MM-DD` dan `HH:MM:SS` (hapus label zona waktu seperti `WIB`).
3. **`tipe` (`CR` / `DB`)**:
   - `CR` = Uang Masuk ke rekening bank (tanda `+`, kolom Kredit mutasi bank).
   - `DB` = Uang Keluar dari rekening bank (tanda `-`, kolom Debet mutasi bank).
   - *Catatan*: Jangan tertukar dengan istilah **DEBET/KREDIT** pada Cash Report SOP (di Cash Report: `CR` bank sejalan dengan `MASUK` → **DEBET**, sedangkan `DB` bank sejalan dengan `KELUAR` → **KREDIT**).
4. **`nominal`**: Angka positif `> 0` (konversi format ribuan titik/koma BRI maupun format Indonesia). Abaikan baris header/footer seperti *"Saldo Awal"*, *"Saldo Akhir"*, atau ringkasan tanpa nominal transaksi.
5. **`saldo`**: Angka saldo berjalan versi bank pada baris tersebut (jika tersedia di PDF).
6. **`uraian`**: Gabungan deskripsi transaksi yang bersih untuk kebutuhan pencarian dan deteksi kata kunci (seperti `FLIPTECH`, `BUNGA`, `ADMIN REKENING`, `TAX`).

---

## 4. Alur Proses 2 Tahap & Proteksi Anti-Double

### Tahap 1 — Upload & Preview Parsing PDF (`Preview / Extract`)
1. User memilih target rekening (atau `Auto`) dan mengunggah 1 file `.pdf`.
2. Hitung hash **SHA-256** file PDF dan cek ke `mutasi_upload_batch.file_hash`:
   - Jika file yang sama persis pernah diunggah, tampilkan status peringatan bahwa file sudah ada di sistem (beri opsi tolak atau mode *replace* secara sadar khusus untuk `finance`/`management`).
3. Ekstrak seluruh baris transaksi menggunakan jalur deterministik (PDF teks) atau render+AI (PDF gambar/vektor).
4. Hitung ringkasan validasi matematis langsung pada hasil preview:
   - `periode_mulai` & `periode_selesai`
   - `saldo_awal_periode` (diturunkan dari baris pertama: `saldo - nominal` jika `CR`, atau `saldo + nominal` jika `DB`)
   - Total `CR` (uang masuk), Total `DB` (uang keluar), `saldo_akhir_periode`
   - **Cek Konsistensi Saldo**: bandingkan `saldo_awal_periode + total_CR - total_DB` terhadap `saldo_akhir_periode` baris terakhir. Jika selisih ≠ 0, tampilkan **peringatan keras** kepada user sebelum disimpan (indikasi ada baris PDF yang terlewat saat parsing).

### Tahap 2 — Simpan Batch Mutasi & Sinkronisasi Matching (`Save`)
1. User memeriksa tabel preview baris mutasi, memperbaiki jika ada baris yang keliru baca, lalu klik Simpan.
2. Simpan **1 baris induk** ke `mutasi_upload_batch` (termasuk `uploaded_by_user_id`, `rekening_id`, `file_hash`, `metode_ekstraksi`, `saldo_awal_periode`, `saldo_akhir_periode`).
3. Untuk setiap baris mutasi, hitung **`dedup_signature`** (hash unik dari kombinasi rekening, tanggal, waktu, tipe, nominal, uraian, dan urutan/saldo):
   - Baris yang `dedup_signature`-nya sudah ada di `mutasi_bank` dilewati (atau dilaporkan jumlah baris yang dilewati) agar upload PDF periode yang tumpang tindih (misal 1–15 Jan lalu 10–31 Jan) **tidak membuat mutasi ganda**.
4. Setelah batch mutasi tersimpan, sistem langsung memicu **Rekonsiliasi Otomatis** (`rekonsiliasi_match`) untuk mencocokkan mutasi baru dengan `transaksi_internal` yang sudah ada.

---

## 5. Keterkaitan dengan Rekonsiliasi & Cash Report
1. **Penyedia Saldo Awal Cash Report**: `mutasi_upload_batch.saldo_awal_periode` menjadi referensi saldo awal saat menghitung kolom **SALDO** berjalan di Cash Report per rekening.
2. **Penyesuaian Baris Mutasi Tanpa Struk**:
   - Baris mutasi yang tidak menemukan pasangan di `transaksi_internal` akan berstatus `BELUM_TERCATAT` (atau terklasifikasi sebagai `Biaya Administrasi / Bunga / Pajak Bank` bila uraian cocok kata kunci bank).
   - Dari menu Rekonsiliasi, Finance dapat mengubah baris tersebut menjadi transaksi resmi di `transaksi_internal` dengan `sumber_pencatatan = 'PENYESUAIAN_MUTASI'` dan mengikatnya lewat `rekonsiliasi_match`, sehingga Cash Report tetap lengkap dan saldo akhir cocok dengan bank.
3. **Hapus Batch Mutasi**:
   - Jika PDF salah upload dan batch dihapus, `ON DELETE CASCADE` pada `mutasi_bank` dan `rekonsiliasi_match` akan membersihkan baris terkait, lalu status `transaksi_internal` yang tadinya cocok harus dihitung ulang oleh mesin rekonsiliasi agar tidak menyisakan status `SESUAI` palsu.

---

## 6. Daftar Kebutuhan Endpoint & UI Minimal
- **Backend**:
  - Endpoint `preview/extract`: terima PDF + pilihan rekening → kembalikan baris hasil parse, metode ekstraksi, status duplikat hash PDF, serta cek konsistensi saldo (`saldo_awal + CR - DB == saldo_akhir`).
  - Endpoint `save`: simpan `mutasi_upload_batch` + baris `mutasi_bank` (dengan skip/dedup `dedup_signature`) + picu rekonsiliasi.
  - Endpoint `list` batch & baris mutasi per rekening/periode + filter status rekonsiliasi.
  - Endpoint `delete` batch mutasi (diikuti kalkulasi ulang status rekonsiliasi `transaksi_internal`).
- **Frontend (`frontend/js/menus/inputMutasi.js`)**:
  - Form upload PDF + selector rekening, tabel preview hasil ekstrak dengan indikator cek keseimbangan saldo, riwayat batch PDF terunggah, serta daftar mutasi per rekening dengan badge `CR`/`DB` dan status rekon.

---

## 7. Acceptance Criteria (Kriteria Uji)
1. Upload PDF teks BRI IBBIZ diparsing deterministik tanpa memanggil Vision AI; jumlah `saldo_awal + total_CR - total_DB` sama persis dengan `saldo_akhir`.
2. Upload PDF kurva vektor BNI Wondr berhasil mengekstrak seluruh baris transaksi dengan tipe `CR`/`DB` dan nominal positif yang tepat.
3. Upload ulang PDF yang sama persis ditolak/ditandai duplikat berdasarkan `mutasi_upload_batch.file_hash`.
4. Upload dua PDF dengan rentang tanggal tumpang tindih tidak menduplikasi baris mutasi yang sama berkat `mutasi_bank.dedup_signature`.
5. Setelah mutasi disimpan, `transaksi_internal` yang sebelumnya berstatus `MUTASI_BELUM_ADA` / `BELUM_REKON` otomatis berubah cocok melalui `rekonsiliasi_match`.
6. User dengan role `staff` ditolak (`403`) saat mencoba mengakses seluruh endpoint mutasi.
