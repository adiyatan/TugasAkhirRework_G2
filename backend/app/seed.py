from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
from pathlib import Path
import shutil
import sqlite3

import fitz

from app.core.database import get_connection, init_db
from app.schemas.mutasi import MutasiRowInput
from app.services.mutasi_parser import parse_bri_ibbiz_text
from app.services.mutasi_service import compute_balance_summary, compute_dedup_signature
from app.services.rekonsiliasi_service import auto_reconcile_mutasi_batch
from app.services.storage import ensure_storage_layout, safe_stored_filename, storage_root

REPO_ROOT = Path(__file__).resolve().parents[2]
BUKTI_DIR = REPO_ROOT / "Bukti_Terstruktur_Januari_2026"
BNI_PDF_NAME = "BNI_Mutasi_Januari_2026.pdf"
BNI_PDF_PATH = BUKTI_DIR / "06_Mutasi_Rekening" / BNI_PDF_NAME
BRI_PDF_NAME = "Mutasi Rekening BRI-Januari 2026.pdf"
BRI_PDF_PATH = BUKTI_DIR / "06_Mutasi_Rekening" / BRI_PDF_NAME

FOLDER_TO_TAB_TYPE: dict[str, str] = {
    "01_Normal": "normal",
    "02_Transfer_Flip": "flip",
    "03_Slip_Gaji": "slip_gaji",
    "04_Reimburse": "reimburse",
}

SLOT_PREFIX_TO_SLOT: dict[str, str] = {
    "Slot_A_": "A",
    "Slot_B_": "B",
    "Slot_C_": "C",
}

# Seluruh 84 baris mutasi BNI (Taplus Muda 1783680837 a.n. ILHAM NAWAN RASYID, Januari 2026)
# Saldo Awal: 2,180,712 | Total Pemasukan: +20,426,175 | Total Pengeluaran: -13,049,913 | Saldo Akhir: 9,556,974
BNI_MUTASI_JAN_2026: list[tuple[str, str, str, str, int, int]] = [
    # Halaman 1 (11 baris)
    ("2026-01-01", "16:28:32", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 800353, 1380359),
    ("2026-01-01", "16:32:26", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 640350, 740009),
    ("2026-01-01", "17:05:13", "Transfer | JAGO SYARIAH - ILHAM NAWAN RASYID", "CR", 210000, 950009),
    ("2026-01-02", "10:14:26", "Transfer | PERMATA - EDIT ESTETIKA", "CR", 903000, 1853009),
    ("2026-01-02", "11:20:07", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 1129075, 723934),
    ("2026-01-03", "21:33:26", "Transfer | BCA - NURHADI NUGRAHA", "CR", 400000, 1123934),
    ("2026-01-05", "09:52:24", "Transfer | BNI - PT TOKOPEDIA", "CR", 57489, 1181423),
    ("2026-01-05", "09:55:09", "Transfer | BNI - PT AIRPAY INTERNATIONAL INDONESIA", "CR", 412294, 1593717),
    ("2026-01-05", "09:57:12", "Transfer | BNI - MUHAMAD ALI SHODIQI", "CR", 195000, 1788717),
    ("2026-01-06", "09:13:58", "Transfer | BANK JATIM - RETNO PALUPI", "CR", 2115000, 3903717),
    ("2026-01-06", "14:23:45", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 200394, 3703323),
    # Halaman 2 (15 baris)
    ("2026-01-06", "18:43:38", "Pembayaran Qris | GRIYA KARDUS - KLATEN (KAB)", "DB", 70000, 3633323),
    ("2026-01-07", "07:36:38", "Virtual Account | PT INDONESIA COMNETS PLUS - ELING MUHAMMAD FALAH", "DB", 256800, 3376523),
    ("2026-01-07", "07:36:38", "Biaya | PT INDONESIA COMNETS PLUS - ELING MUHAMMAD FALAH", "DB", 1750, 3374773),
    ("2026-01-07", "13:53:43", "Transfer | BCA - CLUB SEHAT SURABAYA CV", "CR", 41500, 3416273),
    ("2026-01-07", "14:23:33", "Pembayaran | TAGIHAN BPJS KETENAGAKERJAAN - BPJS_KETENAGAKERJAA", "DB", 53407, 3362866),
    ("2026-01-07", "16:33:29", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 73325, 3289541),
    ("2026-01-07", "17:28:09", "Pembayaran Qris | SAMPURNAPRINT - YOGYAKARTA (KOT", "DB", 35000, 3254541),
    ("2026-01-08", "06:19:03", "Transfer | BCA - SEPTIYANI FITRI CAHYANIN", "CR", 515000, 3769541),
    ("2026-01-08", "08:09:12", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 35335, 3734206),
    ("2026-01-08", "11:29:26", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "CR", 15000, 3749206),
    ("2026-01-08", "11:38:55", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 100429, 3648777),
    ("2026-01-08", "14:47:18", "Pembayaran Qris | ENAMPULUH JASOL QR - YOGYAKARTA", "DB", 48000, 3600777),
    ("2026-01-08", "16:03:42", "Pembayaran Qris | METRO BARU PRAMBANAN - KLATEN", "DB", 156000, 3444777),
    ("2026-01-08", "18:50:11", "Virtual Account | SHOPEE-LXXXXXXXXXXD/LXXXXXXXXXXXX", "DB", 98523, 3346254),
    ("2026-01-08", "18:53:42", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 180329, 3165925),
    # Halaman 3 (15 baris)
    ("2026-01-08", "22:48:34", "Transfer | BCA - YENI SARAH H", "CR", 380995, 3546920),
    ("2026-01-08", "22:49:32", "Transfer | BCA - YENI SARAH H", "CR", 221000, 3767920),
    ("2026-01-09", "14:02:10", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 2705329, 1062591),
    ("2026-01-09", "15:51:37", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 200437, 862154),
    ("2026-01-09", "16:02:04", "Pembayaran Qris | SHAFA JOGJA UTARA - SLEMAN (KAB)", "DB", 393500, 468654),
    ("2026-01-09", "21:02:27", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 201858, 266796),
    ("2026-01-10", "10:16:46", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 143326, 123470),
    ("2026-01-10", "10:26:42", "Transfer | BNI - MUHAMAD ALI SHODIQI", "CR", 15000, 138470),
    ("2026-01-12", "15:04:09", "Transfer | BCA - RIKA CHRISTINA", "CR", 103500, 241970),
    ("2026-01-12", "17:18:49", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 35325, 206645),
    ("2026-01-12", "17:22:12", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 35325, 171320),
    ("2026-01-13", "10:53:52", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "CR", 239000, 410320),
    ("2026-01-13", "11:36:53", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 100389, 309931),
    ("2026-01-13", "11:39:50", "Virtual Account | PT. AIRPAY INTERNATIONAL INDONESIA - SHOPEE-IXXXXX", "DB", 108232, 201699),
    ("2026-01-13", "17:22:22", "Transfer | BCA - YENI SARAH H", "CR", 271000, 472699),
    # Halaman 4 (15 baris)
    ("2026-01-13", "17:23:00", "Transfer | BCA - YENI SARAH H", "CR", 271000, 743699),
    ("2026-01-13", "17:23:34", "Transfer | BCA - YENI SARAH HANDAYANI", "CR", 271000, 1014699),
    ("2026-01-13", "17:24:12", "Transfer | BCA - YENI SARAH HANDAYANI", "CR", 271000, 1285699),
    ("2026-01-14", "11:50:13", "Pembayaran Qris | TOKO MANGGALAM QR - SUKOHARJO", "DB", 157571, 1128128),
    ("2026-01-14", "14:24:39", "Transfer | BNI - TINA TRIASIH", "CR", 270000, 1398128),
    ("2026-01-15", "17:38:22", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 40329, 1357799),
    ("2026-01-15", "19:22:32", "Transfer | BCA - WIDJAJA KUSUMANINGSIH", "CR", 200000, 1557799),
    ("2026-01-15", "20:37:52", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 157825, 1399974),
    ("2026-01-16", "10:30:49", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 200433, 1199541),
    ("2026-01-17", "10:32:51", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 74825, 1124716),
    ("2026-01-17", "10:37:34", "Transfer | BNI - MUHAMAD ALI SHODIQI", "DB", 62500, 1062216),
    ("2026-01-17", "10:40:46", "Transfer | BNI - MUHAMAD ALI SHODIQI", "DB", 75000, 987216),
    ("2026-01-17", "11:46:11", "Pembayaran | TIKET KAI - ILHAM NAWAN RASYID", "DB", 189000, 798216),
    ("2026-01-17", "20:18:52", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 90338, 707878),
    ("2026-01-18", "09:45:32", "Pembayaran Qris | TOKO BANGUNAN PERENG ABAD - KLATEN", "DB", 84000, 623878),
    # Halaman 5 (15 baris)
    ("2026-01-18", "17:59:27", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "CR", 3646410, 4270288),
    ("2026-01-18", "18:11:20", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 1265185, 3005103),
    ("2026-01-20", "08:56:16", "Transfer | BANK JATIM - RETNO PALUPI", "CR", 2115000, 5120103),
    ("2026-01-20", "10:59:49", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 200343, 4919760),
    ("2026-01-20", "11:08:22", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "CR", 170000, 5089760),
    ("2026-01-20", "13:52:49", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 70331, 5019429),
    ("2026-01-21", "15:44:04", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "CR", 2751381, 7770810),
    ("2026-01-21", "20:11:40", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 52327, 7718483),
    ("2026-01-22", "06:10:03", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 30344, 7688139),
    ("2026-01-22", "19:08:38", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 130329, 7557810),
    ("2026-01-22", "19:13:17", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 63329, 7494481),
    ("2026-01-22", "19:19:42", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "CR", 63000, 7557481),
    ("2026-01-22", "20:17:16", "Pembayaran | TIKET KAI - ILHAM NAWAN RASYID", "DB", 176000, 7381481),
    ("2026-01-23", "10:46:37", "Transfer | BNI - PT AIRPAY INTERNATIONAL INDONESIA", "CR", 545000, 7926481),
    ("2026-01-24", "08:49:21", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 40725, 7885756),
    # Halaman 6 (13 baris)
    ("2026-01-24", "09:05:43", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "CR", 249000, 8134756),
    ("2026-01-24", "14:25:44", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 780325, 7354431),
    ("2026-01-25", "11:43:46", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 800329, 6554102),
    ("2026-01-26", "16:21:15", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 70165, 6483937),
    ("2026-01-26", "20:03:45", "Transfer | BNI - ERICK APRIANTO HODIONO", "CR", 88000, 6571937),
    ("2026-01-27", "15:10:20", "Transfer | BCA - MISI SEHAT IMANI PT", "CR", 920400, 7492337),
    ("2026-01-28", "16:22:39", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 12830, 7479507),
    ("2026-01-28", "16:28:12", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "CR", 2499545, 9979052),
    ("2026-01-28", "17:39:00", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 200414, 9778638),
    ("2026-01-29", "12:00:23", "Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI", "DB", 168325, 9610313),
    ("2026-01-30", "19:11:21", "Pembayaran Qris | SAMPURNAPRINT - YOGYAKARTA (KOT", "DB", 49000, 9561313),
    ("2026-01-31", "23:59:59", "Lainnya | Bunga", "CR", 661, 9561974),
    ("2026-01-31", "23:59:59", "Biaya | Admin Rekening", "DB", 5000, 9556974),
]

# Seluruh 68 transaksi bersih hasil pengelompokan 111 file unik dari Bukti_Terstruktur_Januari_2026
# Format tuple:
# (tgl, waktu, rekening, tipe, kategori, penerima_pengirim, keterangan, nominal_pokok, biaya_admin_kode_unik, total_mutasi, list_files_with_meta)
# list_files_with_meta: [(filename, jenis_struk, status_file, nominal_raw, ket_raw), ...]
TRANSAKSI_BUKTI_JAN_2026: list[tuple] = [
    (
        "2026-01-01", "16:28:32", "BNI", "KELUAR", "Bahan Baku", "Eling Muhammad Falah",
        "Tepung beras dan giling jagung", 800000, 353, 800353,
        [
            ("photo_2026-01-01_16-28-57.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 800353, "BNI->Flip Tepung beras dan giling jagung"),
            ("photo_2026-01-01_16-29-59.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 800000, "Flip->Eling Muhammad Falah (BRI)"),
        ],
    ),
    (
        "2026-01-01", "16:32:26", "BNI", "KELUAR", "Bahan Baku", "Sutarmo",
        "Mocaf 50 kg", 640000, 350, 640350,
        [
            ("photo_2026-01-01_16-32-50.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 640350, "BNI->Flip Mocaf 50 kg"),
            ("photo_2026-01-01_16-33-39.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 640000, "Flip->Sutarmo (BCA)"),
        ],
    ),
    (
        "2026-01-01", "17:05:13", "BNI", "PINDAH_BUKU", "Transfer Antar Rekening (Pindah Buku)", "Bank Jago Syariah -> BNI",
        "Pindah buku Jago ke BNI (Ongkir 8 Influencer CST Ads Shopee Freemie Des 25)", 210000, 0, 210000,
        [
            ("photo_2026-01-01_17-06-05.jpg", "JAGO", "TERPAKAI_UTAMA", 210000, "Jago->BNI Ilham Nawan Rasyid"),
        ],
    ),
    (
        "2026-01-02", "11:20:07", "BNI", "KELUAR", "Biaya-Gaji Karyawan", "Nita Repi Jayanti",
        "Gaji Tim Produksi Bu Nita Desember 2025", 1128750, 325, 1129075,
        [
            ("photo_2026-01-02_11-20-19.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 1129075, "BNI->Flip Gaji Tim Produksi Bu Nita"),
            ("photo_2026-01-02_11-20-56.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 1128750, "Flip->Nita Repi Jayanti (BRI)"),
            ("photo_2026-01-02_11-17-59.jpg", "NOTA_FISIK_SLIP_RESI", "TERPAKAI_NOTA_PENDUKUNG", 1128750, "Slip Gaji Staff Produksi Nita Repi Jayanti Des 2025"),
        ],
    ),
    (
        "2026-01-03", "08:57:00", "Bank Jago (Kantong 1)", "KELUAR", "Biaya-Ongkir", "Winarni",
        "Ongkir Affiliate", 43000, 0, 43000,
        [
            ("photo_2026-01-03_08-58-40.jpg", "JAGO", "TERPAKAI_UTAMA", 43000, "Jago->Winarni Ongkir Affiliate"),
        ],
    ),
    (
        "2026-01-03", "21:33:26", "BNI", "MASUK", "Pendapatan Usaha (Penjualan Lainnya)", "Nurhadi Nugraha (BCA)",
        "Transfer masuk BCA BI-FAST ke BNI (Ref 9503120260103213325406FA48BE61010B8)", 400000, 0, 400000,
        [
            ("photo_2026-01-05_11-22-59.jpg", "BCA", "TERPAKAI_UTAMA", 400000, "m-Transfer BCA->BNI 03/01/2026 21:33:26"),
        ],
    ),
    (
        "2026-01-05", "09:52:24", "BNI", "MASUK", "Pendapatan Usaha (Penjualan Lainnya)", "PT Tokopedia",
        "Penarikan dana penjualan Tokopedia ke BNI (*0837)", 57489, 0, 57489,
        [
            ("photo_2026-01-05_09-52-50.jpg", "SHOPEE_TOKOPEDIA", "TERPAKAI_UTAMA", 57489, "Penarikan Tokopedia ID 3551008829798384823"),
        ],
    ),
    (
        "2026-01-05", "09:55:09", "BNI", "MASUK", "Pendapatan Usaha (Penjualan Lainnya)", "Shopee (PT Airpay International Indonesia)",
        "Penarikan dana Saldo Penjual Shopee ke BNI (*0837)", 412294, 0, 412294,
        [
            ("photo_2026-01-05_09-55-33.jpg", "SHOPEE_TOKOPEDIA", "TERPAKAI_UTAMA", 412294, "Penarikan Saldo Penjual Shopee 212376921055429762"),
        ],
    ),
    (
        "2026-01-05", "09:57:12", "BNI", "MASUK", "Pendapatan Usaha (Penjualan Lainnya)", "Muhamad Ali Shodiqi",
        "Penjualan Satvika Bhoga", 195000, 0, 195000,
        [
            ("photo_2026-01-05_09-57-49.jpg", "WONDR_BNI", "TERPAKAI_UTAMA", 195000, "Wondr BNI Ali->Ilham penjualan satvika bhoga"),
        ],
    ),
    (
        "2026-01-06", "09:13:58", "BNI", "MASUK", "Pendapatan Usaha (Workshop)", "Retno Palupi (Bank Jatim)",
        "DP SMA Plosoklaten", 2115000, 0, 2115000,
        [
            ("photo_2026-01-06_09-27-39.jpg", "BANK_JATIM", "TERPAKAI_UTAMA", 2115000, "Bank Jatim->BNI DP SMA Plosoklaten"),
        ],
    ),
    (
        "2026-01-06", "14:23:45", "BNI", "PINDAH_BUKU", "Transfer Antar Rekening (Pindah Buku)", "BRI Operasional (174601000418533)",
        "Uang operasional (Pindah buku BNI -> Flip -> BRI Operasional)", 200000, 394, 200394,
        [
            ("photo_2026-01-06_14-25-48.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 200394, "BNI->Flip Uang operasional"),
            ("photo_2026-01-06_14-26-54.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 200000, "Flip->Ilham BRI 174601000418533"),
        ],
    ),
    (
        "2026-01-06", "18:43:38", "BNI", "KELUAR", "Biaya-Operasional", "Griya Kardus Klaten",
        "Pembayaran QRIS Griya Kardus Klaten (Kardus kemasan)", 70000, 0, 70000,
        [
            ("photo_2026-01-07_08-28-34.jpg", "BNI_QRIS", "TERPAKAI_UTAMA", 70000, "QRIS Griya Kardus 06-01-2026 18:43:38"),
        ],
    ),
    (
        "2026-01-07", "07:36:38", "BNI", "KELUAR", "Biaya-Operasional", "PLN (Eling Muhammad Falah)",
        "Tagihan Listrik PLN THBLTAG 202601 (IDPEL 131100601584)", 256800, 1750, 258550,
        [
            ("photo_2026-01-07_08-29-35.jpg", "BNI_VA", "TERPAKAI_UTAMA", 258550, "VA PLN 256.800 + Admin 1.750"),
        ],
    ),
    (
        "2026-01-07", "14:23:33", "BNI", "KELUAR", "Biaya-Gaji Karyawan", "BPJS Ketenagakerjaan",
        "Iuran BPJS Ketenagakerjaan PU Bulan 01/2026 (NPP 24240215)", 53407, 0, 53407,
        [
            ("photo_2026-01-07_14-24-06.jpg", "BNI_VA", "TERPAKAI_UTAMA", 53407, "BPJS Ketenagakerjaan PU 01/2026"),
        ],
    ),
    (
        "2026-01-07", "16:33:29", "BNI", "KELUAR", "Biaya-Ongkir", "Winarni",
        "Ongkir Sampel dan Good Food", 73000, 325, 73325,
        [
            ("photo_2026-01-07_16-34-03.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 73325, "BNI->Flip Ongkir Sampel dan Good Food"),
            ("photo_2026-01-07_16-36-20.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 73000, "Flip->Winarni (BCA)"),
        ],
    ),
    (
        "2026-01-07", "17:28:09", "BNI", "KELUAR", "Biaya-Perlengkapan Kantor dan Administrasi", "Sampurnaprint Yogyakarta",
        "Pembayaran QRIS Sampurnaprint Yogyakarta", 35000, 0, 35000,
        [
            ("photo_2026-01-07_17-28-35.jpg", "BNI_QRIS", "TERPAKAI_UTAMA", 35000, "QRIS Sampurnaprint"),
        ],
    ),
    (
        "2026-01-08", "06:19:03", "BNI", "MASUK", "Pendapatan Usaha (Penjualan Lainnya)", "Septiyani Fitri Cahyaningrum (BCA)",
        "Penjualan Mieee gluten free (myBCA BI-FAST)", 515000, 0, 515000,
        [
            ("photo_2026-01-08_09-21-46.jpg", "BCA", "TERPAKAI_UTAMA", 515000, "myBCA->BNI Mieee gluten free"),
        ],
    ),
    (
        "2026-01-08", "08:09:12", "BNI", "KELUAR", "Biaya-Ongkir", "Tsana Natasha Dini",
        "Ongkir CST Cilacap", 35000, 335, 35335,
        [
            ("photo_2026-01-08_08-09-30.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 35335, "BNI->Flip Ongkir CST Cilacap"),
            ("photo_2026-01-08_08-10-08.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 35000, "Flip->Tsana Natasha Dini"),
        ],
    ),
    (
        "2026-01-08", "11:29:26", "BNI", "MASUK", "Pendapatan Usaha (Penjualan Lainnya)", "Pelanggan (via Flip)",
        "Penjualan Freemie Instan 1", 15000, 0, 15000,
        [
            ("photo_2026-01-08_11-30-34.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_UTAMA", 15000, "Flip->BNI Ilham Penjualan Freemie Instan 1"),
        ],
    ),
    (
        "2026-01-08", "11:38:55", "BNI", "PINDAH_BUKU", "Transfer Antar Rekening (Pindah Buku)", "Ilham Nawan Rasyid (BRI)",
        "Uang Konsumsi Diskusi Akhir Tahun Lokality", 100000, 429, 100429,
        [
            ("photo_2026-01-08_11-39-23.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 100429, "BNI->Flip Uang Konsumsi Diskusi Akhir Tahun"),
            ("photo_2026-01-08_11-42-39.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 100000, "Flip->Ilham (BRI)"),
        ],
    ),
    (
        "2026-01-08", "14:47:18", "BNI", "KELUAR", "Biaya-Konsumsi", "Enampuluh Jasol QR Yogyakarta",
        "Pembayaran QRIS Enampuluh Jasol QR Yogyakarta", 48000, 0, 48000,
        [
            ("photo_2026-01-08_14-51-01.jpg", "BNI_QRIS", "TERPAKAI_UTAMA", 48000, "QRIS Enampuluh Jasol QR"),
        ],
    ),
    (
        "2026-01-08", "16:03:42", "BNI", "KELUAR", "Biaya-Operasional", "Metro Baru Prambanan",
        "Pembayaran QRIS Metro Baru Prambanan Klaten", 156000, 0, 156000,
        [
            ("photo_2026-01-08_16-04-09.jpg", "BNI_QRIS", "TERPAKAI_UTAMA", 156000, "QRIS Metro Baru Prambanan"),
        ],
    ),
    (
        "2026-01-08", "18:50:11", "BNI", "KELUAR", "Bahan Baku", "Shopee (ORIGINALSTOREIND & The Nut House)",
        "Sarung Tangan Nitrile Isi 100 Pcs & 1kg Pure Chili Powder / Cabe Bubuk", 98523, 0, 98523,
        [
            ("photo_2026-01-08_18-51-19.jpg", "BNI_VA", "TERPAKAI_UTAMA", 98523, "BNI VA Shopee 88060895364932077"),
            ("photo_2026-01-08_18-30-53.jpg", "SHOPEE_TOKOPEDIA", "TERPAKAI_NOTA_PENDUKUNG", 98523, "Keranjang Shopee Sarung Tangan + Cabe Bubuk"),
        ],
    ),
    (
        "2026-01-08", "18:53:42", "BNI", "KELUAR", "Biaya-Gaji Karyawan", "Freelance Admin",
        "Fee Freelance Admin 2 hari", 180000, 329, 180329,
        [
            ("photo_2026-01-08_18-54-01.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 180329, "BNI->Flip Fee Freelance Admin 2 hari"),
        ],
    ),
    (
        "2026-01-09", "14:02:10", "BNI", "PINDAH_BUKU", "Transfer Antar Rekening (Pindah Buku)", "Muhamad Ali Shodiqi, Eling M. Falah, & Ilham N. Rasyid",
        "Bundle Flip: Bagi Hasil Des 25 Shodiqi (1.264.860) + Falah (1.064.860) + Marketing Profit Share Saving (375.283)", 2705003, 326, 2705329,
        [
            ("photo_2026-01-09_14-04-06.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 2705329, "BNI->Flip Bundle Bagi Hasil Des 25"),
            ("photo_2026-01-09_14-04-55.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 1264860, "Flip->Muhamad Ali Shodiqi (BRI)"),
            ("photo_2026-01-09_14-05-15.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 1064860, "Flip->Eling Muhammad Falah (BRI)"),
            ("photo_2026-01-09_14-05-34.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 375283, "Flip->Jago Ilham Nawan Rasyid"),
        ],
    ),
    (
        "2026-01-09", "15:51:37", "BNI", "PINDAH_BUKU", "Transfer Antar Rekening (Pindah Buku)", "BRI Operasional (174601000418533)",
        "Uang operasional (Pindah buku BNI -> Flip -> BRI Operasional)", 200000, 437, 200437,
        [
            ("photo_2026-01-09_15-52-34.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 200437, "BNI->Flip Uang operasional"),
            ("photo_2026-01-09_15-53-31.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 200000, "Flip->Ilham BRI 174601000418533"),
        ],
    ),
    (
        "2026-01-09", "16:02:04", "BNI", "KELUAR", "Biaya-Operasional", "Shafa Jogja Utara Sleman",
        "Pembayaran QRIS Shafa Jogja Utara Sleman", 393500, 0, 393500,
        [
            ("photo_2026-01-09_16-03-31.jpg", "BNI_QRIS", "TERPAKAI_UTAMA", 393500, "QRIS Shafa Jogja Utara"),
        ],
    ),
    (
        "2026-01-09", "21:02:27", "BNI", "KELUAR", "Biaya-Operasional", "PLN (via Flip)",
        "Listrik Januari 2026", 201500, 358, 201858,
        [
            ("photo_2026-01-09_21-02-41.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 201858, "BNI->Flip Listrik Januari 2026"),
        ],
    ),
    (
        "2026-01-10", "10:16:46", "BNI", "KELUAR", "Biaya-Ongkir", "Winarni",
        "Ongkir 9 paket", 143000, 326, 143326,
        [
            ("photo_2026-01-10_10-17-09.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 143326, "BNI->Flip Ongkir 9 paket"),
            ("photo_2026-01-10_10-59-14.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 143000, "Flip->Winarni (BCA)"),
        ],
    ),
    (
        "2026-01-10", "10:26:42", "BNI", "MASUK", "Pendapatan Usaha (Penjualan Lainnya)", "Muhamad Ali Shodiqi",
        "Ongkir Bu Sri Sudaryani (Wondr BNI)", 15000, 0, 15000,
        [
            ("photo_2026-01-10_10-27-08.jpg", "WONDR_BNI", "TERPAKAI_UTAMA", 15000, "Wondr BNI Ali->Ilham ongkir Bu Sri Sudaryani"),
        ],
    ),
    (
        "2026-01-12", "11:03:51", "BRI Operasional", "KELUAR", "Biaya-Pembelian Aset", "William Hartoko",
        "Beli Mesin Gilingan Pasta (BRImo 1746...533 -> Flip -> BCA)", 350000, 325, 350325,
        [
            ("photo_2026-01-12_11-04-21.jpg", "BRIMO", "TERPAKAI_UTAMA", 350325, "BRImo->Flip Beli gilingan pasta"),
            ("photo_2026-01-12_11-07-44.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 350000, "Flip->William Hartoko (BCA)"),
        ],
    ),
    (
        "2026-01-12", "17:22:12", "BNI", "KELUAR", "Biaya-Ongkir", "Tsana Natasha Dini",
        "Ongkir CST", 35000, 325, 35325,
        [
            ("photo_2026-01-12_17-22-27.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 35325, "BNI->Flip Ongkir CST"),
            ("photo_2026-01-12_17-23-16.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 35000, "Flip->Tsana Natasha Dini"),
        ],
    ),
    (
        "2026-01-13", "11:36:53", "BNI", "KELUAR", "Biaya-Pembelian Aset", "Muhammad Triyono",
        "Band continuous sealer 4 buah", 100000, 389, 100389,
        [
            ("photo_2026-01-13_11-37-18.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 100389, "BNI->Flip Band continuous sealer 4 buah"),
            ("photo_2026-01-13_11-41-26.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 100000, "Flip->Muhammad Triyono (Mandiri)"),
        ],
    ),
    (
        "2026-01-13", "11:39:50", "BNI", "KELUAR", "Biaya-Operasional", "Shopee (TOKORAK.ID)",
        "Bagus Serapair Refill 450ml Charcoal x8", 108232, 0, 108232,
        [
            ("photo_2026-01-13_11-40-10.jpg", "BNI_VA", "TERPAKAI_UTAMA", 108232, "BNI VA Shopee 8806085725209099"),
            ("photo_2026-01-13_11-40-46.jpg", "SHOPEE_TOKOPEDIA", "TERPAKAI_NOTA_PENDUKUNG", 108232, "Rincian Pesanan Shopee Bagus Serapair x8"),
        ],
    ),
    (
        "2026-01-14", "11:50:13", "BNI", "KELUAR", "Biaya-Operasional", "Toko Manggalam QR Sukoharjo",
        "Pembayaran QRIS Toko Manggalam QR Sukoharjo", 157571, 0, 157571,
        [
            ("photo_2026-01-14_11-50-28.jpg", "BNI_QRIS", "TERPAKAI_UTAMA", 157571, "QRIS Toko Manggalam QR"),
        ],
    ),
    (
        "2026-01-15", "17:38:22", "BNI", "KELUAR", "Biaya-Ongkir", "Winarni",
        "Ongkir 3 paket", 40000, 329, 40329,
        [
            ("photo_2026-01-15_17-38-46.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 40329, "BNI->Flip Ongkir 3 paket"),
            ("photo_2026-01-15_17-39-45.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 40000, "Flip->Winarni (BCA)"),
        ],
    ),
    (
        "2026-01-15", "20:37:52", "BNI", "KELUAR", "Biaya-Ongkir", "Tsana Natasha Dini & Flip",
        "Bundle Flip: Ongkir Perlengkapan & Mi Workshop Kediri (145.000) + Langganan Flip Freedom Starter (12.500)", 157500, 325, 157825,
        [
            ("photo_2026-01-15_20-40-42.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 157825, "BNI->Flip Bundle Ongkir Kediri + Langganan Flip"),
            ("photo_2026-01-15_20-41-47.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 145000, "Flip->Tsana Natasha Dini (BCA)"),
            ("photo_2026-01-15_20-42-24.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 12500, "Flip Langganan Paket Freedom Starter"),
        ],
    ),
    (
        "2026-01-16", "10:30:49", "BNI", "PINDAH_BUKU", "Transfer Antar Rekening (Pindah Buku)", "BRI Operasional (174601000418533)",
        "Uang operasional (Pindah buku BNI -> Flip -> BRI Operasional)", 200000, 433, 200433,
        [
            ("photo_2026-01-16_10-31-25.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 200433, "BNI->Flip Uang operasional"),
            ("photo_2026-01-16_10-32-23.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 200000, "Flip->Ilham BRI 174601000418533"),
        ],
    ),
    (
        "2026-01-17", "10:32:51", "BNI", "PINDAH_BUKU", "Transfer Antar Rekening (Pindah Buku)", "Ilham Nawan Rasyid (BRI)",
        "Iuran Kelas Keuangan", 74500, 325, 74825,
        [
            ("photo_2026-01-17_10-33-45.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 74825, "BNI->Flip Iuran Kelas Keuangan"),
            ("photo_2026-01-17_10-34-19.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 74500, "Flip->Ilham BRI"),
        ],
    ),
    (
        "2026-01-17", "10:37:34", "BNI", "KELUAR", "Biaya-Operasional", "Muhamad Ali Shodiqi",
        "Iuran Kelas Busdev", 62500, 0, 62500,
        [
            ("photo_2026-01-17_10-38-29.jpg", "BNI_TRANSFER", "TERPAKAI_UTAMA", 62500, "BNI->Muhamad Ali Shodiqi Iuran Kelas Busdev"),
        ],
    ),
    (
        "2026-01-17", "10:40:46", "BNI", "KELUAR", "Biaya-Perlengkapan Kantor dan Administrasi", "Muhamad Ali Shodiqi (Reimburse Toko Piala Jaya Kediri)",
        "Plakat Workshop SMAN 1 Plosoklaten", 75000, 0, 75000,
        [
            ("photo_2026-01-17_10-41-34.jpg", "BNI_TRANSFER", "TERPAKAI_UTAMA", 75000, "BNI->Ali Reimburse Plakat Workshop SMAN 1 Plosoklaten"),
            ("photo_2026-01-17_10-37-42.jpg", "WONDR_BNI", "TERPAKAI_NOTA_PENDUKUNG", 75000, "QRIS Wondr Ali di Toko Piala Jaya Kediri"),
        ],
    ),
    (
        "2026-01-17", "10:43:00", "Bank Jago (Kantong 1)", "KELUAR", "Biaya-Operasional", "Muhamad Ali Shodiqi (Reimburse XDT-Facebook Ads)",
        "Saldo Meta Ads Freemie (Reimburse pembayaran XDT-Facebook Ads tgl 16 Jan)", 80000, 0, 80000,
        [
            ("photo_2026-01-17_10-44-19.jpg", "JAGO", "TERPAKAI_UTAMA", 80000, "Jago->Ali Reimburse Saldo Meta Ads Freemie"),
            ("photo_2026-01-16_12-47-37.jpg", "WONDR_BNI", "TERPAKAI_NOTA_PENDUKUNG", 80000, "Wondr Ali pembayaran VA XDT-Facebook Ads"),
        ],
    ),
    (
        "2026-01-17", "11:46:43", "BNI", "KELUAR", "Biaya-Transportasi", "PT KAI",
        "Tiket Kereta Singasari PWS -> KD (Berangkat 21 Jan 2026, Kode DMS9HV6)", 189000, 0, 189000,
        [
            ("photo_2026-01-17_11-48-12.jpg", "BNI_VA", "TERPAKAI_UTAMA", 189000, "BNI Pembayaran KAI Singasari"),
        ],
    ),
    (
        "2026-01-17", "20:18:52", "BNI", "KELUAR", "Bahan Baku", "Aisah",
        "Tempe produksi 5 Jan", 90000, 338, 90338,
        [
            ("photo_2026-01-17_20-21-21.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 90338, "BNI->Flip Tempe produksi 5 Jan"),
            ("photo_2026-01-17_20-22-25.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 90000, "Flip->Aisah (BRI)"),
        ],
    ),
    (
        "2026-01-18", "09:45:32", "BNI", "KELUAR", "Biaya-Perbaikan Bangunan", "Toko Bangunan Pereng Abad Klaten",
        "Pembayaran QRIS Toko Bangunan Pereng Abad Klaten", 84000, 0, 84000,
        [
            ("photo_2026-01-18_09-45-45.jpg", "BNI_QRIS", "TERPAKAI_UTAMA", 84000, "QRIS Toko Bangunan Pereng Abad"),
        ],
    ),
    (
        "2026-01-18", "18:11:20", "BNI", "PINDAH_BUKU", "Transfer Antar Rekening (Pindah Buku)", "Ilham Nawan Rasyid (BRI)",
        "Bagi Hasil Desember 2025 Ilham", 1264860, 325, 1265185,
        [
            ("photo_2026-01-18_18-11-51.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 1265185, "BNI->Flip Bagi Hasil Desember 25 Ilham"),
            ("photo_2026-01-18_18-12-31.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 1264860, "Flip->Ilham (BRI)"),
        ],
    ),
    (
        "2026-01-20", "08:56:16", "BNI", "MASUK", "Pendapatan Usaha (Workshop)", "Retno Palupi (Bank Jatim)",
        "Pelunasan SMAN 1 Plosoklaten", 2115000, 0, 2115000,
        [
            ("photo_2026-01-20_09-39-28.jpg", "BANK_JATIM", "TERPAKAI_UTAMA", 2115000, "Bank Jatim->BNI Pelunasan SMAN 1 Plosoklaten"),
        ],
    ),
    (
        "2026-01-20", "10:59:49", "BNI", "PINDAH_BUKU", "Transfer Antar Rekening (Pindah Buku)", "BRI Operasional (174601000418533)",
        "Uang operasional (Pindah buku BNI -> Flip -> BRI Operasional)", 200000, 343, 200343,
        [
            ("photo_2026-01-20_11-00-07.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 200343, "BNI->Flip Uang operasional"),
            ("photo_2026-01-20_11-05-55.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 200000, "Flip->Ilham BRI 174601000418533"),
        ],
    ),
    (
        "2026-01-20", "11:08:22", "BNI", "MASUK", "Pendapatan Usaha (Penjualan Lainnya)", "Ibu Hardiyati Kowapi (via Flip)",
        "Penjualan Bu Hardiyati Kowapi", 170000, 0, 170000,
        [
            ("photo_2026-01-20_11-10-51.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_UTAMA", 170000, "Flip->BNI Penjualan Bu Hardiyati Kowapi"),
        ],
    ),
    (
        "2026-01-20", "13:52:49", "BNI", "KELUAR", "Bahan Baku", "Aisah",
        "Tempe produksi 20 Januari 2026", 70000, 331, 70331,
        [
            ("photo_2026-01-20_13-53-11.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 70331, "BNI->Flip Tempe produksi 20 Januari 2026"),
            ("photo_2026-01-20_13-55-11.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 70000, "Flip->Aisah (BRI)"),
        ],
    ),
    (
        "2026-01-21", "20:11:40", "BNI", "KELUAR", "Biaya-Ongkir", "Winarni",
        "Ongkir 6 paket", 52000, 327, 52327,
        [
            ("photo_2026-01-21_20-12-03.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 52327, "BNI->Flip Ongkir 6 paket"),
            ("photo_2026-01-21_20-12-47.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 52000, "Flip->Winarni (BCA)"),
        ],
    ),
    (
        "2026-01-22", "06:10:04", "BNI", "KELUAR", "Biaya-Sosial", "Legowo Sumarno",
        "Iuran Jumat Berkah Januari 2026", 30000, 344, 30344,
        [
            ("photo_2026-01-22_06-10-29.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 30344, "BNI->Flip Iuran JumatBerkah Januari 2026"),
            ("photo_2026-01-22_06-11-16.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 30000, "Flip->Legowo Sumarno (BRI)"),
        ],
    ),
    (
        "2026-01-22", "19:08:38", "BNI", "KELUAR", "Biaya-Gaji Karyawan", "Yola Darma Dhaifulla",
        "Fee Freelance Dokumentasi", 130000, 329, 130329,
        [
            ("photo_2026-01-22_19-08-49.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 130329, "BNI->Flip Fee Freelance Dokumentasi"),
            ("photo_2026-01-22_19-09-46.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 130000, "Flip->Yola Darma Dhaifulla (BRI)"),
        ],
    ),
    (
        "2026-01-22", "19:13:17", "BNI", "KELUAR", "Biaya-Konsumsi", "Bakso Kikil & Urat Srengat Indah (Reimburse Ilham)",
        "Konsumsi Makan Sore Workshop (3x Bakso Kikil + 3x Es Jeruk)", 63000, 329, 63329,
        [
            ("photo_2026-01-22_19-13-28.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 63329, "BNI->Flip Konsumsi Makan Sore Workshop"),
            ("photo_2026-01-22_19-14-31.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 63000, "Flip->Ilham (BRI)"),
            ("photo_2026-01-22_19-11-40.jpg", "NOTA_FISIK_SLIP_RESI", "TERPAKAI_NOTA_PENDUKUNG", 63000, "Nota fisik Bakso Kikil & Urat Srengat Indah"),
        ],
    ),
    (
        "2026-01-22", "19:19:42", "BNI", "MASUK", "Pendapatan Usaha (Workshop)", "SMA N 1 Plosoklaten (via Flip)",
        "Penjualan SMA N 1 Plosoklaten", 63000, 0, 63000,
        [
            ("photo_2026-01-22_19-20-48.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_UTAMA", 63000, "Flip->BNI Penjualan SMA N 1 Plosoklaten"),
        ],
    ),
    (
        "2026-01-22", "20:17:18", "BNI", "KELUAR", "Biaya-Transportasi", "PT KAI",
        "Tiket Kereta Malioboro Ekspres KD -> SLO (Kode U7W99F7)", 176000, 0, 176000,
        [
            ("photo_2026-01-22_20-17-43.jpg", "BNI_VA", "TERPAKAI_UTAMA", 176000, "BNI Pembayaran KAI Malioboro Ekspres"),
        ],
    ),
    (
        "2026-01-23", "10:46:37", "BNI", "MASUK", "Pendapatan Usaha (Penjualan Lainnya)", "Septiyani (ShopeePay)",
        "Pencairan ShopeePay Septiyani ke BNI (Waktu selesai 23 Jan 2026 10:46)", 545000, 0, 545000,
        [
            ("photo_2026-01-24_10-50-38.jpg", "SHOPEE_TOKOPEDIA", "TERPAKAI_UTAMA", 545000, "ShopeePay->BNI Septiyani 23 Jan 2026 10:46"),
        ],
    ),
    (
        "2026-01-24", "08:49:21", "BNI", "KELUAR", "Biaya-Ongkir", "Tsana Natasha Dini (J&T Cargo)",
        "Ongkir Club Sehat / PT Misi Sehat Imani (Resi J&T Cargo 201351368363)", 40400, 325, 40725,
        [
            ("photo_2026-01-24_08-49-44.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 40725, "BNI->Flip Ongkir Club Sehat"),
            ("photo_2026-01-24_08-53-33.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 40400, "Flip->Tsana Natasha Dini (BCA)"),
            ("photo_2026-01-24_08-47-05.jpg", "NOTA_FISIK_SLIP_RESI", "TERPAKAI_NOTA_PENDUKUNG", 40400, "Resi fisik J&T Cargo 201351368363"),
        ],
    ),
    (
        "2026-01-24", "14:25:44", "BNI", "KELUAR", "Bahan Baku", "Sri Harsini",
        "Jagung 100 kg", 780000, 325, 780325,
        [
            ("photo_2026-01-24_14-26-01.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 780325, "BNI->Flip Jagung 100 kg"),
            ("photo_2026-01-24_14-30-01.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 780000, "Flip->Sri Harsini (BCA)"),
        ],
    ),
    (
        "2026-01-25", "11:43:46", "BNI", "KELUAR", "Biaya-Pembelian Aset", "Eling Muhammad Falah",
        "Ember Saringan Keranjang Jagung", 800000, 329, 800329,
        [
            ("photo_2026-01-25_11-44-01.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 800329, "BNI->Flip Ember Saringan Keranjang Jagung"),
            ("photo_2026-01-25_11-50-30.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 800000, "Flip->Eling Muhammad Falah (BRI)"),
        ],
    ),
    (
        "2026-01-26", "16:21:15", "BNI", "KELUAR", "Biaya-Ongkir", "Winarsih Kristiani",
        "Ongkir Perlengkapan Workshop", 69840, 325, 70165,
        [
            ("photo_2026-01-26_16-21-40.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 70165, "BNI->Flip Ongkir Perlengkapan Workshop"),
            ("photo_2026-01-26_16-22-47.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 69840, "Flip->Winarsih Kristiani (BCA)"),
        ],
    ),
    (
        "2026-01-26", "17:31:00", "Bank Jago (Kantong 1)", "KELUAR", "Biaya-Ongkir", "Winarni",
        "Ongkir Shopee Affiliate 3", 19000, 0, 19000,
        [
            ("photo_2026-01-26_17-33-49.jpg", "JAGO", "TERPAKAI_UTAMA", 19000, "Jago->Winarni Ongkir Shopee Affiliate 3"),
        ],
    ),
    (
        "2026-01-28", "16:22:39", "BNI", "KELUAR", "Biaya-Operasional", "PT Fliptech Lentera Inspirasi Pertiwi",
        "Langganan Flip Freedom Starter Januari 2026", 12500, 330, 12830,
        [
            ("photo_2026-01-28_16-23-44.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 12830, "BNI->Flip Langganan Flip Januari 2026"),
            ("photo_2026-01-28_16-24-11.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 12500, "Flip Langganan Paket Freedom Starter"),
        ],
    ),
    (
        "2026-01-28", "17:39:00", "BNI", "KELUAR", "Pendapatan/Beban Lain", "Eling Muhammad Falah",
        "Cash Bon Falah Januari 2026", 200000, 414, 200414,
        [
            ("photo_2026-01-28_17-39-22.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 200414, "BNI->Flip Cash Bon Falah Januari 2026"),
            ("photo_2026-01-28_17-41-48.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 200000, "Flip->Eling Muhammad Falah (BRI)"),
        ],
    ),
    (
        "2026-01-29", "12:00:23", "BNI", "KELUAR", "Biaya-Perbaikan Bangunan", "Krakatau Megatama Pemala",
        "Pipa Galvanis Kabel PLN 25inch 1 mm", 168000, 325, 168325,
        [
            ("photo_2026-01-29_12-00-54.jpg", "BNI_TO_FLIP", "TERPAKAI_UTAMA", 168325, "BNI->Flip Pipa Galvanis Kabel PLN 25inch 1 mm"),
            ("photo_2026-01-29_12-02-23.jpg", "FLIP_TO_RECIPIENT", "TERPAKAI_PENDUKUNG_FLIP", 168000, "Flip->Krakatau Megatama Pemala (BCA)"),
        ],
    ),
    (
        "2026-01-30", "17:40:00", "Kas Operasional", "KELUAR", "Biaya-Ongkir", "Wahana Express (Ibu Helmy Surabaya)",
        "Ongkir Wahana Express Resi 5LYK2561 / INV/2026/0003 (Ibu Helmy)", 13000, 0, 13000,
        [
            ("photo_2026-01-30_17-40-26.jpg", "NOTA_FISIK_SLIP_RESI", "TERPAKAI_UTAMA", 13000, "Resi Wahana Express 5LYK2561 + Invoice INV/2026/0003"),
        ],
    ),
    (
        "2026-01-30", "19:11:21", "BNI", "KELUAR", "Biaya-Perlengkapan Kantor dan Administrasi", "Sampurnaprint Yogyakarta",
        "Pembayaran QRIS Sampurnaprint Yogyakarta", 49000, 0, 49000,
        [
            ("photo_2026-01-30_19-11-44.jpg", "BNI_QRIS", "TERPAKAI_UTAMA", 49000, "QRIS Sampurnaprint"),
        ],
    ),
    (
        "2026-01-30", "22:06:00", "Bank Jago (Kantong 1)", "KELUAR", "Biaya-Operasional", "Muhamad Ali Shodiqi (Reimburse XDT-Facebook Ads)",
        "Meta Ads Freemie (Reimburse pembayaran XDT-Facebook Ads tgl 29 Jan)", 125000, 0, 125000,
        [
            ("photo_2026-01-30_22-25-13.jpg", "JAGO", "TERPAKAI_UTAMA", 125000, "Jago->Ali Reimburse Meta Ads Freemie"),
            ("photo_2026-01-29_09-17-03.jpg", "WONDR_BNI", "TERPAKAI_NOTA_PENDUKUNG", 125000, "Wondr Ali pembayaran VA XDT-Facebook Ads"),
        ],
    ),
]


def is_database_empty() -> bool:
    """Mengembalikan True jika tabel transaksi, mutasi, batch, dan file bukti belum terisi."""
    init_db()
    with closing(get_connection()) as conn:
        counts = [
            conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "transaksi_internal",
                "mutasi_bank",
                "mutasi_upload_batch",
                "file_bukti_log",
            )
        ]
    return all(count == 0 for count in counts)


def reset_transactional_data() -> None:
    """Menghapus seluruh data transaksi, mutasi, log bukti, rekonsiliasi, dan file storage."""
    init_db()
    with closing(get_connection()) as conn:
        conn.executescript(
            """
            DELETE FROM rekonsiliasi_match;
            DELETE FROM file_bukti_log;
            DELETE FROM mutasi_bank;
            DELETE FROM mutasi_upload_batch;
            DELETE FROM transaksi_internal;
            DELETE FROM upload_staging;
            DELETE FROM sqlite_sequence
                WHERE name IN (
                    'rekonsiliasi_match',
                    'file_bukti_log',
                    'mutasi_bank',
                    'mutasi_upload_batch',
                    'transaksi_internal'
                );
            """
        )
        conn.commit()

    root = storage_root()
    for subdir in ("files", "staging"):
        target = root / subdir
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
    ensure_storage_layout()


def _index_bukti_files(bukti_dir: Path) -> dict[str, tuple[Path, str, str]]:
    """Mengindeks seluruh 111 file bukti unik dari folder terstruktur (non-duplikat)."""
    if not bukti_dir.is_dir():
        raise FileNotFoundError(f"Folder bukti tidak ditemukan: {bukti_dir}")

    index: dict[str, tuple[Path, str, str]] = {}
    for path in sorted(bukti_dir.rglob("*.jpg")):
        rel = path.relative_to(bukti_dir).parts
        if len(rel) < 4 or rel[0] not in FOLDER_TO_TAB_TYPE:
            continue
        tab_type = FOLDER_TO_TAB_TYPE[rel[0]]
        slot = next(
            (slot_code for prefix, slot_code in SLOT_PREFIX_TO_SLOT.items() if rel[2].startswith(prefix)),
            None,
        )
        if slot is None:
            continue
        index[path.name] = (path, tab_type, slot)
    return index


def _resolve_tx_accounts(
    rekening: str,
    tipe: str,
    penerima_pengirim: str,
) -> tuple[str, str | None]:
    """Memetakan rekening sumber & tujuan (khususnya PINDAH_BUKU) ke kode_akun G2."""
    if tipe != "PINDAH_BUKU":
        return rekening, None
    if "Bank Jago Syariah -> BNI" in penerima_pengirim:
        return "Bank Jago (Kantong 1)", "BNI"
    if "BRI Operasional" in penerima_pengirim or "Ilham Nawan Rasyid (BRI)" in penerima_pengirim:
        return rekening, "BRI Operasional"
    if "Bank Jago (Kantong 2)" in penerima_pengirim or "Ilham N. Rasyid" in penerima_pengirim:
        return rekening, "Bank Jago (Kantong 2)"
    return rekening, None


def _compute_batch_signatures(rekening_id: int, rows: list[MutasiRowInput]) -> list[str]:
    counts: dict[tuple, int] = {}
    signatures: list[str] = []
    for row in rows:
        key = (
            rekening_id,
            row.tanggal,
            row.waktu,
            row.tipe,
            f"{round(float(row.nominal), 2):.2f}",
            " ".join(row.uraian.split()).strip().upper(),
        )
        occ = counts.get(key, 0)
        counts[key] = occ + 1
        signatures.append(
            compute_dedup_signature(
                rekening_id=rekening_id,
                tanggal=row.tanggal,
                waktu=row.waktu,
                tipe=row.tipe,
                nominal=row.nominal,
                uraian=row.uraian,
                saldo=row.saldo,
                occurrence=occ,
            )
        )
    return signatures


def _insert_mutasi_batch(
    conn: sqlite3.Connection,
    *,
    rekening_id: int,
    no_rekening: str,
    uploaded_by_user_id: int,
    nama_file: str,
    file_hash: str,
    metode_ekstraksi: str,
    rows: list[MutasiRowInput],
) -> int:
    summary = compute_balance_summary(rows)
    assert summary.balance_valid, f"Saldo mutasi {nama_file} tidak konsisten: {summary}"
    signatures = _compute_batch_signatures(rekening_id, rows)

    batch_id = conn.execute(
        """
        INSERT INTO mutasi_upload_batch (
            rekening_id, uploaded_by_user_id, nama_file, file_hash,
            metode_ekstraksi, periode_mulai, periode_selesai,
            saldo_awal_periode, saldo_akhir_periode, jumlah_baris
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rekening_id,
            uploaded_by_user_id,
            nama_file,
            file_hash,
            metode_ekstraksi,
            summary.periode_mulai,
            summary.periode_selesai,
            summary.saldo_awal_periode,
            summary.saldo_akhir_periode,
            len(rows),
        ),
    ).lastrowid

    for row, sig in zip(rows, signatures, strict=True):
        conn.execute(
            """
            INSERT INTO mutasi_bank (
                batch_id, rekening_id, no_rekening, tanggal, waktu,
                uraian, tipe, nominal, saldo, dedup_signature
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id,
                rekening_id,
                no_rekening,
                row.tanggal,
                row.waktu,
                row.uraian,
                row.tipe,
                row.nominal,
                row.saldo,
                sig,
            ),
        )

    return int(batch_id)


def _load_bni_mutasi_rows() -> tuple[list[MutasiRowInput], str]:
    running_saldo = 2180712
    total_cr = 0
    total_db = 0
    rows: list[MutasiRowInput] = []
    for tgl, waktu, uraian, tipe, nominal, saldo_expected in BNI_MUTASI_JAN_2026:
        if tipe == "CR":
            running_saldo += nominal
            total_cr += nominal
        else:
            running_saldo -= nominal
            total_db += nominal
        assert running_saldo == saldo_expected, (
            f"Saldo BNI tidak cocok pada {tgl} {waktu}: {running_saldo} vs {saldo_expected}"
        )
        rows.append(
            MutasiRowInput(
                tanggal=tgl,
                waktu=waktu,
                uraian=uraian,
                tipe=tipe,
                nominal=float(nominal),
                saldo=float(saldo_expected),
            )
        )
    assert total_cr == 20426175, f"Total CR BNI salah: {total_cr}"
    assert total_db == 13049913, f"Total DB BNI salah: {total_db}"
    assert running_saldo == 9556974, f"Saldo Akhir BNI salah: {running_saldo}"

    if BNI_PDF_PATH.is_file():
        file_hash = hashlib.sha256(BNI_PDF_PATH.read_bytes()).hexdigest()
    else:
        file_hash = hashlib.sha256(BNI_PDF_NAME.encode("utf-8")).hexdigest()
    return rows, file_hash


def _load_bri_mutasi_rows() -> tuple[list[MutasiRowInput], str]:
    if not BRI_PDF_PATH.is_file():
        raise FileNotFoundError(f"PDF mutasi BRI tidak ditemukan: {BRI_PDF_PATH}")
    pdf_bytes = BRI_PDF_PATH.read_bytes()
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        parsed = parse_bri_ibbiz_text([page.get_text() for page in doc])
    assert parsed is not None, "Gagal mem-parse mutasi BRI IBBIZ dari PDF"
    assert len(parsed.rows) == 14, f"Jumlah baris BRI harus 14, terbaca {len(parsed.rows)}"
    total_cr = sum(r.nominal for r in parsed.rows if r.tipe == "CR")
    total_db = sum(r.nominal for r in parsed.rows if r.tipe == "DB")
    assert round(total_cr) == 178309, f"Total CR BRI salah: {total_cr}"
    assert round(total_db) == 22066136, f"Total DB BRI salah: {total_db}"
    assert parsed.rows[-1].saldo is not None and round(parsed.rows[-1].saldo) == 192643952

    rows = [
        MutasiRowInput(
            tanggal=r.tanggal,
            waktu=r.waktu,
            uraian=r.uraian,
            tipe=r.tipe,
            nominal=r.nominal,
            saldo=r.saldo,
        )
        for r in parsed.rows
    ]
    return rows, hashlib.sha256(pdf_bytes).hexdigest()


def restore_missing_seed_files() -> int:
    """Menyalin ulang file bukti dari Bukti_Terstruktur jika tercatat di DB tetapi hilang di storage/files."""
    if not BUKTI_DIR.is_dir():
        return 0
    files_dir = ensure_storage_layout() / "files"
    with closing(get_connection()) as conn:
        rows = conn.execute(
            "SELECT filename, orig_filename, file_hash FROM file_bukti_log"
        ).fetchall()

    missing = [row for row in rows if not (files_dir / row["filename"]).is_file()]
    if not missing:
        return 0

    bukti_index = _index_bukti_files(BUKTI_DIR)
    restored = 0
    for row in missing:
        entry = bukti_index.get(row["orig_filename"])
        if not entry:
            continue
        src_path = entry[0]
        file_bytes = src_path.read_bytes()
        if hashlib.sha256(file_bytes).hexdigest() != row["file_hash"]:
            continue
        (files_dir / row["filename"]).write_bytes(file_bytes)
        restored += 1
    return restored


def seed_januari_2026(*, reset: bool = False, only_if_empty: bool = False) -> dict:
    """Mengisi database SQLite dengan dataset Januari 2026 dan menyalin file bukti ke storage."""
    init_db()
    if only_if_empty and not is_database_empty():
        restored = restore_missing_seed_files()
        result: dict[str, object] = {"seeded": False, "reason": "database_not_empty"}
        if restored:
            result["restored_files"] = restored
        return result

    if reset:
        reset_transactional_data()
    elif not is_database_empty():
        raise RuntimeError(
            "Database sudah berisi data transaksi/mutasi. Gunakan reset=True (--reset) untuk mengisi ulang."
        )

    storage_root_path = ensure_storage_layout()
    files_dir = storage_root_path / "files"
    bukti_index = _index_bukti_files(BUKTI_DIR)

    bni_rows, bni_hash = _load_bni_mutasi_rows()
    bri_rows, bri_hash = _load_bri_mutasi_rows()

    created_tx_ids: list[int] = []
    seeded_filenames: set[str] = set()

    with closing(get_connection()) as conn:
        rekening_map = {
            row["kode_akun"]: {"id": int(row["id"]), "no_rekening": row["no_rekening"]}
            for row in conn.execute("SELECT id, kode_akun, no_rekening FROM rekening_perusahaan").fetchall()
        }
        kategori_map = {
            row["nama_kategori"]: int(row["id"])
            for row in conn.execute("SELECT id, nama_kategori FROM kategori_sop").fetchall()
        }
        user_row = conn.execute(
            "SELECT id FROM users WHERE username = 'finance' LIMIT 1"
        ).fetchone()
        if not user_row:
            user_row = conn.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1").fetchone()
        assert user_row is not None, "User default belum tersedia di database"
        finance_user_id = int(user_row["id"])

        conn.execute("BEGIN IMMEDIATE")
        try:
            for (
                tgl,
                waktu,
                rekening,
                tipe,
                kategori,
                penerima_pengirim,
                keterangan,
                nominal_pokok,
                biaya_admin,
                total_mutasi,
                files_meta,
            ) in TRANSAKSI_BUKTI_JAN_2026:
                sumber_kode, tujuan_kode = _resolve_tx_accounts(rekening, tipe, penerima_pengirim)
                sumber_id = rekening_map[sumber_kode]["id"]
                tujuan_id = rekening_map[tujuan_kode]["id"] if tujuan_kode else None
                kategori_id = kategori_map[kategori]

                first_fname = files_meta[0][0]
                if first_fname not in bukti_index:
                    raise FileNotFoundError(f"File bukti tidak ditemukan di {BUKTI_DIR}: {first_fname}")
                tab_type = bukti_index[first_fname][1]

                tx_id = int(
                    conn.execute(
                        """
                        INSERT INTO transaksi_internal (
                            staging_id, created_by_user_id, nama_admin, tanggal_input,
                            sumber_pencatatan, tab_type, tanggal_transaksi, waktu_transaksi,
                            rekening_sumber_id, rekening_tujuan_id, tipe, kategori_id,
                            penerima_pengirim, keterangan, nominal_pokok,
                            biaya_admin_kode_unik, total_mutasi
                        ) VALUES (NULL, ?, 'Chikaristin', '2026-02-01', 'INPUT_STRUK', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            finance_user_id,
                            tab_type,
                            tgl,
                            waktu,
                            sumber_id,
                            tujuan_id,
                            tipe,
                            kategori_id,
                            penerima_pengirim,
                            keterangan,
                            float(nominal_pokok),
                            float(biaya_admin),
                            float(total_mutasi),
                        ),
                    ).lastrowid
                )
                created_tx_ids.append(tx_id)

                for fname, jenis_struk, status_file, nominal_raw, ket_raw in files_meta:
                    if fname not in bukti_index:
                        raise FileNotFoundError(f"File bukti tidak ditemukan di {BUKTI_DIR}: {fname}")
                    src_path, _, slot = bukti_index[fname]
                    file_bytes = src_path.read_bytes()
                    file_hash = hashlib.sha256(file_bytes).hexdigest()
                    stored_name = safe_stored_filename(fname, file_hash, slot)
                    (files_dir / stored_name).write_bytes(file_bytes)

                    conn.execute(
                        """
                        INSERT INTO file_bukti_log (
                            transaksi_internal_id, slot, filename, orig_filename, file_hash,
                            jenis_struk, status_file, nominal_raw, tanggal_waktu_raw, keterangan_raw
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            tx_id,
                            slot,
                            stored_name,
                            fname,
                            file_hash,
                            jenis_struk,
                            status_file,
                            float(nominal_raw),
                            f"{tgl} {waktu}",
                            ket_raw,
                        ),
                    )
                    seeded_filenames.add(fname)

            bni_batch_id = _insert_mutasi_batch(
                conn,
                rekening_id=rekening_map["BNI"]["id"],
                no_rekening=rekening_map["BNI"]["no_rekening"],
                uploaded_by_user_id=finance_user_id,
                nama_file=BNI_PDF_NAME,
                file_hash=bni_hash,
                metode_ekstraksi="Seed Januari 2026 (Terverifikasi)",
                rows=bni_rows,
            )
            bri_batch_id = _insert_mutasi_batch(
                conn,
                rekening_id=rekening_map["BRI"]["id"],
                no_rekening=rekening_map["BRI"]["no_rekening"],
                uploaded_by_user_id=finance_user_id,
                nama_file=BRI_PDF_NAME,
                file_hash=bri_hash,
                metode_ekstraksi="Deterministik (Teks PDF)",
                rows=bri_rows,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    rekon_bni = auto_reconcile_mutasi_batch(bni_batch_id)
    rekon_bri = auto_reconcile_mutasi_batch(bri_batch_id)

    return {
        "seeded": True,
        "bni_inserted": len(bni_rows),
        "bri_inserted": len(bri_rows),
        "transaksi_internal_count": len(created_tx_ids),
        "file_bukti_count": len(seeded_filenames),
        "rekon_bni": rekon_bni,
        "rekon_bri": rekon_bri,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.seed",
        description="Seeding data Januari 2026 (mutasi BNI/BRI, transaksi struk, file bukti, dan auto-rekonsiliasi).",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--if-empty",
        action="store_true",
        help="Jalankan seeding hanya jika tabel transaksi & mutasi masih kosong (default).",
    )
    mode.add_argument(
        "--reset",
        action="store_true",
        help="Hapus data transaksi/mutasi/rekonsiliasi yang ada lalu isi ulang dari seed Januari 2026.",
    )
    parser.add_argument(
        "--env-file",
        metavar="PATH",
        default=None,
        help="Baca konfigurasi dari file .env pada path ini.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.env_file:
        env_path = Path(args.env_file).expanduser()
        if not env_path.is_file():
            parser.error(f"File .env tidak ditemukan: {args.env_file}")

    result = seed_januari_2026(reset=args.reset, only_if_empty=not args.reset)
    if not result["seeded"]:
        restored = result.get("restored_files", 0)
        if restored:
            print(f"Memulihkan {restored} file bukti yang hilang ke storage/files.")
        print("Database sudah terisi; seeding otomatis dilewati (gunakan --reset untuk isi ulang).")
        return

    print("=== SEEDING JANUARI 2026 BERHASIL ===")
    print(f"Mutasi BNI        : {result['bni_inserted']} baris (Saldo Akhir Rp9.556.974)")
    print(f"Mutasi BRI        : {result['bri_inserted']} baris (Saldo Akhir Rp192.643.952)")
    print(f"Transaksi Internal: {result['transaksi_internal_count']} transaksi")
    print(f"File Bukti Log    : {result['file_bukti_count']} file (tersimpan di storage/files)")
    print(f"Rekonsiliasi BNI  : {result['rekon_bni']}")
    print(f"Rekonsiliasi BRI  : {result['rekon_bri']}")


if __name__ == "__main__":
    main()
