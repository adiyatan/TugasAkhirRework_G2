# Requirement Modul Input Struk

Dokumen ini menjadi acuan kerja pembagian tugas **Backend** dan **Frontend** untuk menu **Input Struk** (`input_struk`) pada sistem keuangan **PT Lokal Komoditi Indonesia**, selaras dengan skema SQLite di [database.py](../backend/app/core/database.py).

---

## 1. Tujuan & Hak Akses (RBAC)
1. Memastikan setiap bukti transaksi (nota, struk transfer, resi, slip gaji, reimburse) masuk ke pembukuan internal secara **terstruktur**, **anti-duplikat**, dan **siap dicocokkan** dengan mutasi bank.
2. **Hak Akses Menu** (`require_menu("input_struk")`):
   - Role `staff`, `finance`, dan `management` dapat mengakses ekstraksi, review, dan simpan struk.
   - Identitas penginput (`created_by_user_id` dan `nama_admin`) **wajib** diambil otomatis dari user yang login (tidak boleh di-hardcode atau diisi bebas oleh client).
   - **Batasan Role `staff`**:
     - `staff` tidak memiliki akses ke menu `input_mutasi` dan `rekonsiliasi`. Petunjuk kecocokan mutasi saat review cukup menampilkan status ringkas (misal: *"Ditemukan indikasi kecocokan di mutasi"* / *"Belum ada di mutasi"*), tanpa membocorkan saldo atau uraian detail rekening bank.
     - Penghapusan transaksi hanya diizinkan untuk `finance`/`management` (atau `staff` hanya untuk transaksi miliknya sendiri yang statusnya masih `BELUM_REKON`).

---

## 2. Pembagian 4 Mode Tab & 3 Slot Gambar

| Mode (`tab_type`) | Slot A (Wajib) | Slot B | Slot C | Aturan Bisnis & Validasi Wajib |
| :--- | :--- | :--- | :--- | :--- |
| `normal` | 1+ bukti bayar/terima sah (atau nota fisik jika `is_cash = true`) | Opsional (rincian item belanja) | Tidak dipakai | - Tolak screenshot status *"Belum Bayar"* (kecuali `is_cash = true`).<br>- Tolak struk transfer **Flip** (arahkan ke tab `flip`).<br>- Tolak pengirim dari `rekening_dikecualikan` (arahkan ke tab `reimburse`).<br>- Jika `is_cash = true`, kunci rekening ke `Kas Operasional`.<br>- Jika pengirim & penerima sama-sama `rekening_perusahaan` yang berbeda, kunci `tipe = PINDAH_BUKU` dan `kategori = Transfer Antar Rekening (Pindah Buku)`. |
| `flip` | **Tepat 1** struk Bank → PT Fliptech (Flip) | **Minimal 1** (bisa 1..N untuk bundle) struk Flip → Penerima Akhir | Opsional (nota/resi) | - `total_mutasi` diambil dari Slot A (termasuk kode unik 3 digit).<br>- `nominal_pokok` diambil dari penjumlahan Slot B; nama penerima digabung.<br>- `biaya_admin_kode_unik = total_mutasi - nominal_pokok`.<br>- **Blokir simpan** jika selisih `< 0` atau `> Rp1.000` (indikasi foto bukan pasangan).<br>- Peringatkan jika tanggal Slot A ≠ Slot B.<br>- Jika tujuan di Slot B adalah `rekening_perusahaan`, kunci `tipe = PINDAH_BUKU` dan isi `rekening_tujuan_id`. |
| `slip_gaji` | 1+ foto Slip Gaji / Rekap Fee | 1+ bukti Transfer Gaji (transfer langsung atau pasangan Bank→Flip + Flip→Karyawan) | Tidak dipakai | - Kunci `tipe = KELUAR`.<br>- Kategori dibatasi ke `Biaya-Gaji Karyawan` atau `Pendapatan/Beban Lain`.<br>- **Tanggal & waktu transaksi wajib diambil dari Slot B** (waktu transfer, bukan bulan periode di Slip Gaji).<br>- Beri peringatan jika nominal di slip ≠ nominal transfer.<br>- Jika Slot B via Flip, selisih kode unik tetap maksimal Rp1.000. |
| `reimburse` | 1+ nota belanja awal / struk talangan pribadi | 1+ bukti transfer penggantian **dari rekening perusahaan** | Tidak dipakai | - Kunci `tipe = KELUAR`.<br>- **Tanggal, waktu, dan rekening sumber wajib diambil dari Slot B** (saat kas perusahaan keluar mengganti).<br>- **Blokir** jika pengirim Slot B masih berasal dari `rekening_dikecualikan`.<br>- **Blokir** jika selisih nominal Nota Awal (Slot A) dan Transfer Penggantian (Slot B) `> Rp1.000`. |

---

### 2.1 Kenapa Struk Dipisah Jadi Slot A/B/C (Prinsip: 1 Kejadian Kas = 1 Transaksi)

Di lapangan, **1 kejadian uang keluar/masuk sering terdiri dari lebih dari 1 foto bukti**, dan ada foto yang **tidak boleh dicatat sebagai transaksi berdiri sendiri**. Jika sistem memperlakukan `"1 foto = 1 transaksi"`, maka akan terjadi pencatatan ganda (*double entry*), nominal meleset, atau tanggal buku salah.

Tiga alasan utama pemisahan slot:
1. **Mencegah Double Nominal**: Pada Transfer Flip dan Reimburse, uang berpindah dua tahap (Bank → Flip → Vendor, atau Karyawan → Toko lalu Perusahaan → Karyawan). Menggabungkan Slot A dan Slot B dalam satu sesi memastikan hanya terbentuk **1 baris `transaksi_internal`**, sedangkan semua foto tetap tersimpan di `file_bukti_log` dengan peran berbeda (`TERPAKAI_UTAMA` vs `TERPAKAI_PENDUKUNG_FLIP` / `TERPAKAI_NOTA_PENDUKUNG`).
2. **Memisahkan Konteks Barang/Penerima vs Bukti Mutasi Bank**: Foto Bank → Flip tidak menyebut nama vendor akhir, dan foto Slip Gaji hanya menyebut bulan periode gaji (bukan tanggal uang ditransfer). Slot A dan Slot B saling melengkapi dalam satu transaksi.
3. **Menjaga 1-to-1 Alignment dengan Mutasi Bank & Cash Report**: Di mutasi bank, 1 transfer Flip (meski untuk beberapa penerima sekaligus) tetap muncul sebagai 1 baris debet. Maka di `transaksi_internal` dan Cash Report wajib menjadi 1 baris agar bisa dicocokkan di `rekonsiliasi_match`.

**Contoh Kasus Nyata di Dataset Uji (`Bukti_Terstruktur_Januari_2026`):**

| Mode | Contoh Folder Uji | Isi Foto per Slot | Kenapa Harus Digabung Jadi 1 Transaksi |
| :--- | :--- | :--- | :--- |
| `flip` | [02_Transfer_Flip / Eling_Muhammad_Falah_800353](../Bukti_Terstruktur_Januari_2026/02_Transfer_Flip/2026-01-01_Eling_Muhammad_Falah_800353) | **Slot A**: BNI → PT Fliptech `Rp800.353` (`01-01-2026 16:28:32`)<br>**Slot B**: Flip → Eling M. Falah `Rp800.000` (*Tepung beras & giling jagung*) | Yang terpotong di mutasi BNI hanya `Rp800.353` (sudah termasuk kode unik `Rp353`). Jika diinput terpisah akan tercatat keluar `Rp1.600.353`. Kasus *bundle* seperti [2026-01-09_Muhamad_Ali_Shodiqi_Elin_2705329](../Bukti_Terstruktur_Januari_2026/02_Transfer_Flip/2026-01-09_Muhamad_Ali_Shodiqi_Elin_2705329) punya 1 Slot A + 3 Slot B yang tetap harus jadi 1 baris transaksi. |
| `slip_gaji` | [03_Slip_Gaji / Nita_Repi_Jayanti_1129075](../Bukti_Terstruktur_Januari_2026/03_Slip_Gaji/2026-01-02_Nita_Repi_Jayanti_1129075) | **Slot A**: Slip Gaji *Bulan Desember 2025* total `Rp1.128.750`<br>**Slot B**: BNI → Flip `Rp1.129.075` & Flip → Nita `Rp1.128.750` (`02-01-2026`) | Slip gaji hanya rincian, bukan bukti kas keluar. Kas baru keluar pada `2026-01-02` sebesar `Rp1.129.075` dari BNI. |
| `reimburse` | [04_Reimburse / Muhamad_Ali_Shodiqi_Reim_75000](../Bukti_Terstruktur_Januari_2026/04_Reimburse/2026-01-17_Muhamad_Ali_Shodiqi_Reim_75000) | **Slot A**: QRIS Wondr rekening pribadi `******096` ke *TOKO PIALA JAYA KEDIRI* `Rp75.000` (`09:28:30 WIB`)<br>**Slot B**: BNI perusahaan mengganti ke `568158096` `Rp75.000` (`10:40:46 WIB`, *Plakat Workshop SMAN 1 Plosoklaten*) | Rekening `*096` bukan rekening perusahaan, jadi QRIS `09:28:30` tidak ada di mutasi bank perusahaan. Yang dicatat ke kas adalah penggantian dari BNI perusahaan pada `10:40:46`, sementara toko tujuan diambil dari Slot A. |

---

### 2.2 Cara Kerja & Contoh Penggunaan Vision AI (`Multi-Image + Signals`)

Vision AI **tidak dipanggil per foto secara terpisah**, melainkan **1 kali panggilan multimodal** yang menerima seluruh gambar dalam 1 batch upload dengan label posisi slotnya (`SLOT A`, `SLOT B`, `SLOT C`).

1. **Input yang Dikirim ke Vision AI (1 Request)**:
   - **Prompt Konteks Dinamis** dari tabel master DB: mode `tab_type` aktif, daftar `rekening_perusahaan` + nomor rekeningnya, daftar 14 `kategori_sop`, daftar `rekening_dikecualikan` (misal `*096`), serta aturan khusus per slot.
   - **Daftar Gambar Berlabel Slot**: contoh untuk kasus Reimburse di atas → teks `"SLOT A - File 1"` + gambar QRIS Wondr `*096`, lalu teks `"SLOT B - File 1"` + gambar BNI transfer perusahaan.

2. **Format Output Vision AI (2 Bagian dalam 1 JSON)**:
   - **Bagian 1 — Field Transaksi Gabungan**: `tanggal_transaksi`, `waktu_transaksi`, `rekening`, `tipe`, `kategori`, `penerima_pengirim`, `keterangan`, `nominal_pokok`, `biaya_admin_kode_unik`, `total_mutasi`, `jenis_struk`.
   - **Bagian 2 — Objek `signals` (Fakta Mentah per Slot)**: AI melaporkan fakta terobservasi tanpa mengambil keputusan rule sendiri, misalnya:
     - `slot_a_is_unpaid_order`, `slot_a_is_flip_to_fliptech`, `slot_a_is_flip_to_recipient`
     - `slot_a_sender_account_digits`, `slot_a_recipient_account_digits`, `slot_a_amount`, `slot_a_date`, `slot_a_time`
     - `slot_b_is_flip_to_recipient`, `slot_b_sender_account_digits`, `slot_b_recipient_account_digits`, `slot_b_sum_amount`, `slot_b_date`, `slot_b_time`

3. **Contoh Alur Eksekusi Nyata (Kasus Reimburse `Rp75.000`)**:
   - Vision AI membaca Slot A (`******096`, `TOKO PIALA JAYA KEDIRI`, `Rp75.000`, `09:28:30`) dan Slot B (BNI perusahaan, tujuan `568158096`, `Rp75.000`, `10:40:46`, *"Plakat Workshop SMAN 1 Plosoklaten"*).
   - AI mengembalikan `signals`: `slot_a_sender_account_digits = "096"`, `slot_a_amount = 75000`, `slot_b_sum_amount = 75000`, `slot_b_date = "2026-01-17"`, `slot_b_time = "10:40:46"`.
   - **Backend menjalankan rule deterministik**:
     - Memastikan Slot B bukan dari rekening dikecualikan (`*096`).
     - Memastikan `|75000 - 75000| <= 1000`.
     - Mengunci `tipe = KELUAR` dan memaksa `tanggal_transaksi` + `waktu_transaksi` memakai data **Slot B (`10:40:46`)**, bukan jam belanja pribadi (`09:28:30`).
   - *Sebaliknya*, jika foto QRIS `*096` tadi salah di-upload di tab `normal`, backend melihat `slot_a_sender_account_digits = "096"` dan langsung memblokir dengan pesan pindah ke tab `reimburse`.

---

## 3. Alur Proses 2 Tahap & Proteksi Anti-Double

### Tahap 1 — Ekstraksi & Staging (`Extract`)
1. Terima upload multipart: `tab_type`, `is_cash`, `slot_a` (wajib), `slot_b`, `slot_c`.
2. Simpan file sementara ke area staging dan buat 1 baris di tabel `upload_staging` dengan `status = 'OPEN'`, `user_id` pengupload, `expires_at` (misal +2 jam), dan `manifest_json` (berisi posisi slot dan hash **SHA-256** tiap file).
3. **Cek Duplikat Hash SHA-256 (Tahap 1)**:
   - Tolak jika ada 2 file identik di dalam batch upload yang sama.
   - Cek setiap `file_hash` ke tabel `file_bukti_log`. Jika sudah ada, masukkan ke daftar `errors` (memblokir tombol Simpan) beserta referensi ID transaksi sebelumnya.
4. **Ekstraksi Terstruktur (Vision AI)**:
   - Daftar rekening, daftar kategori SOP, dan daftar rekening dikecualikan **dibaca dari tabel master** (`rekening_perusahaan`, `kategori_sop`, `rekening_dikecualikan`), bukan hardcode.
   - AI mengembalikan field transaksi + objek sinyal (`signals`) untuk divalidasi secara deterministik oleh rule pada Bagian 2.
5. **Cek Duplikat Semantik & Petunjuk Mutasi**:
   - Cek apakah di `transaksi_internal` sudah ada baris dengan `tanggal_transaksi`, `rekening_sumber_id`, dan `total_mutasi` identik (±Rp1). Jika ada, tampilkan sebagai `warning` yang butuh konfirmasi sadar dari user (`force_save_duplicate`).
   - Jika `errors` kosong, intip `mutasi_bank` pada `rekening_id` dan rentang tanggal `±1 hari` untuk memberi petunjuk kecocokan awal.

### Tahap 2 — Review Manusia & Simpan Final (`Save`)
1. UI menampilkan foto (Slot A/B/C) berdampingan (*side-by-side*) dengan form hasil ekstraksi; field yang terkunci rule tidak dapat diubah sembarangan.
2. Saat user menekan Simpan, backend **wajib melakukan validasi ulang (anti-bypass UI)**:
   - Pastikan `upload_staging` ada, milik user (atau role berwenang), belum kedaluwarsa, dan `status == 'OPEN'`.
   - **Kunci atomik (anti-double click)**: ubah `upload_staging.status` menjadi `'SAVED'` secara atomik di dalam transaksi database sehingga request kedua dengan `staging_id` yang sama otomatis ditolak.
   - Cek ulang `file_hash` ke `file_bukti_log` (kendala unik di DB menjadi pengaman terakhir).
   - Validasi `rekening_sumber_id`, `rekening_tujuan_id` (wajib ada dan berbeda dari sumber jika `tipe == 'PINDAH_BUKU'`), `kategori_id`, `total_mutasi > 0`, serta aturan khusus per `tab_type`.
   - Cek ulang duplikat semantik apabila `force_save_duplicate == false`.
3. Pindahkan file dari staging ke penyimpanan permanen, lalu simpan dalam 1 transaksi database:
   - **1 baris** di `transaksi_internal` (`sumber_pencatatan = 'INPUT_STRUK'`, `tanggal_input` = tanggal hari ini, `nama_admin` = nama user login).
   - **1..N baris** di `file_bukti_log` sesuai peran file (`TERPAKAI_UTAMA`, `TERPAKAI_PENDUKUNG_FLIP`, `TERPAKAI_NOTA_PENDUKUNG`).
4. Setelah commit berhasil, panggil layanan **Rekonsiliasi Otomatis** agar transaksi baru langsung dicocokkan dengan `mutasi_bank` yang sudah ada.

---

## 4. Pemetaan ke Kebutuhan Output 11 Kolom Cash Report

Data yang disimpan Input Struk harus mampu menghasilkan tampilan **Cash Report** dengan kolom berikut:

1. **TANGGAL INPUT** ← `transaksi_internal.tanggal_input`
2. **NAMA ADMIN** ← `transaksi_internal.nama_admin`
3. **TANGGAL TRANSAKSI** ← `transaksi_internal.tanggal_transaksi` (diurutkan dengan `waktu_transaksi`)
4. **KETERANGAN** ← `transaksi_internal.keterangan` (dilengkapi info pihak `penerima_pengirim` / rincian kode unik bila perlu)
5. **KATEGORI** ← `kategori_sop.nama_kategori`
6. **KETERANGAN UANG MASUK** ← `rekening_sumber.kode_akun` (jika `MASUK`), atau `rekening_tujuan.kode_akun` (jika `PINDAH_BUKU`), kosong jika `KELUAR`
7. **KETERANGAN UANG KELUAR** ← `rekening_sumber.kode_akun` (jika `KELUAR` atau `PINDAH_BUKU`), kosong jika `MASUK`
8. **DEBET** ← `total_mutasi` jika `MASUK` (atau sisi masuk `PINDAH_BUKU`), selain itu `0`
9. **KREDIT** ← `total_mutasi` jika `KELUAR` (atau sisi keluar `PINDAH_BUKU`), selain itu `0`
10. **SALDO** ← Dihitung dinamis secara kronologis (`Saldo Sebelumnya + DEBET - KREDIT`), **tidak disimpan statis di DB**
11. **LAMPIRAN NOTA** ← Daftar tautan/preview dari seluruh baris `file_bukti_log` milik transaksi tersebut

---

## 5. Daftar Kebutuhan Endpoint & UI Minimal
- **Backend**:
  - Endpoint metadata form (daftar `rekening_perusahaan` & `kategori_sop` aktif dari SQLite).
  - Endpoint `extract` (Tahap 1: upload multipart slot A/B/C → preview & sinyal validasi).
  - Endpoint `save` (Tahap 2: simpan terverifikasi + catat `file_bukti_log` + trigger rekon).
  - Endpoint `recent` (riwayat input struk + status rekon + daftar lampiran).
  - Endpoint `delete` transaksi (dengan kontrol role & status rekon) + endpoint penyaji gambar bukti yang aman dari *path traversal*.
- **Frontend (`frontend/js/menus/inputStruk.js`)**:
  - Wizard 3 langkah: (1) Pilih Mode Tab & Upload Slot → (2) Review Side-by-Side Foto vs Form + Banner Error/Warning → (3) Hasil Simpan & Riwayat Terbaru.

---

## 6. Acceptance Criteria (Kriteria Uji)
1. Upload 1 transaksi **Transfer Flip** dengan 1 foto Slot A + 3 foto Slot B (seperti data bundle di `Bukti_Terstruktur_Januari_2026/02_Transfer_Flip/`) hanya menghasilkan **1 baris** `transaksi_internal` dan **4 baris** `file_bukti_log`.
2. Mengunggah ulang file dari folder `05_Duplikat_2026-11-12/` ditolak pada tahap `extract` maupun `save` dengan pesan merujuk transaksi asal.
3. Klik tombol Simpan dua kali berturut-turut untuk `staging_id` yang sama tidak menghasilkan 2 transaksi.
4. Input `slip_gaji` dan `reimburse` menggunakan tanggal dari Slot B, bukan tanggal pada slip/nota Slot A.
5. `PINDAH_BUKU` (misal BNI → BRI Operasional) mengisi `rekening_sumber_id` dan `rekening_tujuan_id` dengan benar sehingga **KETERANGAN UANG KELUAR** dan **KETERANGAN UANG MASUK** tampil akurat.
