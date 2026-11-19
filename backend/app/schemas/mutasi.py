from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class MutasiRekeningPublic(BaseModel):
    id: int
    kode_akun: str
    bank_lembaga: str
    no_rekening: str
    atas_nama: str
    peran: str


class MutasiMetadata(BaseModel):
    rekening_perusahaan: list[MutasiRekeningPublic]


class MutasiRowInput(BaseModel):
    tanggal: str
    waktu: str = "00:00:00"
    uraian: str
    tipe: Literal["CR", "DB"]
    nominal: float = Field(..., gt=0)
    saldo: float | None = None

    @field_validator("uraian")
    @classmethod
    def clean_uraian(cls, value: str) -> str:
        cleaned = " ".join(value.split()).strip()
        if not cleaned:
            raise ValueError("Uraian mutasi tidak boleh kosong")
        return cleaned


class MutasiBalanceSummary(BaseModel):
    periode_mulai: str
    periode_selesai: str
    saldo_awal_periode: float | None = None
    total_cr: float
    total_db: float
    saldo_akhir_periode: float | None = None
    printed_saldo_awal: float | None = None
    printed_saldo_akhir: float | None = None
    expected_saldo_akhir: float | None = None
    selisih_saldo: float | None = None
    balance_valid: bool


class MutasiSaveRequest(BaseModel):
    rekening_id: int
    no_rekening: str | None = None
    nama_file: str = Field(..., min_length=1)
    file_hash: str = Field(..., min_length=64, max_length=64)
    metode_ekstraksi: str = Field(..., min_length=1)
    rows: list[MutasiRowInput] = Field(..., min_length=1)
    replace_existing: bool = False
