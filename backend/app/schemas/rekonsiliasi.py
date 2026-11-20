from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RekonMatchRequest(BaseModel):
    transaksi_id: int
    mutasi_ids: list[int] = Field(..., min_length=1)
    catatan: str = ""


class RekonPenyesuaianRequest(BaseModel):
    mutasi_id: int
    kategori_id: int
    tipe: Literal["MASUK", "KELUAR", "PINDAH_BUKU"]
    rekening_sumber_id: int | None = None
    rekening_tujuan_id: int | None = None
    penerima_pengirim: str = ""
    keterangan: str = ""
    catatan: str = ""


class RekonAutoRunRequest(BaseModel):
    rekening_id: int | None = None
