from pydantic import BaseModel


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
