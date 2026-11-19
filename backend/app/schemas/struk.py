from typing import Literal

from pydantic import BaseModel, Field


class RekeningPerusahaanPublic(BaseModel):
    id: int
    kode_akun: str
    bank_lembaga: str
    no_rekening: str
    atas_nama: str
    peran: str
    is_cash: bool


class KategoriSopPublic(BaseModel):
    id: int
    no_urut: int
    nama_kategori: str
    kelompok: str


class RekeningDikecualikanPublic(BaseModel):
    id: int
    nama_pemilik: str
    potongan_no_rek: str
    keterangan: str


class StrukMetadata(BaseModel):
    rekening_perusahaan: list[RekeningPerusahaanPublic]
    kategori_sop: list[KategoriSopPublic]
    rekening_dikecualikan: list[RekeningDikecualikanPublic]
    tabs: list[str]


class StrukTransactionFields(BaseModel):
    tanggal_transaksi: str
    waktu_transaksi: str
    rekening_sumber_id: int
    rekening_tujuan_id: int | None = None
    tipe: Literal["MASUK", "KELUAR", "PINDAH_BUKU"]
    kategori_id: int
    penerima_pengirim: str = ""
    keterangan: str = ""
    nominal_pokok: int = Field(..., ge=0)
    biaya_admin_kode_unik: int = Field(..., ge=0)
    total_mutasi: int = Field(..., gt=0)


class StrukSaveRequest(StrukTransactionFields):
    staging_id: str = Field(..., min_length=1)
    force_save_duplicate: bool = False


class StrukUpdateRequest(StrukTransactionFields):
    pass
