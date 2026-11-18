
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# BankTransaction untuk memvalidasi hasil ekstraksi transaksi rekening koran BNI atau BRI.
class BankTransaction(BaseModel):
    """
    Satu baris transaksi hasil ekstraksi rekening koran.

    Menggunakan konvensi mutasi bank:
    - Debet  = uang keluar
    - Kredit = uang masuk

    Untuk BNI, nominal negatif dikonversi ke Debet
    dan nominal positif dikonversi ke Kredit.
    """

    tanggal_transaksi: date
    keterangan: str

    debet: Decimal = Field(
        default=Decimal("0"),
        ge=0
    )

    kredit: Decimal = Field(
        default=Decimal("0"),
        ge=0
    )

    saldo: Decimal

    @field_validator("keterangan")
    @classmethod
    def clean_keterangan(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "Keterangan transaksi tidak boleh kosong."
            )

        return value

    @model_validator(mode="after")
    def validate_debet_kredit(self):
        """
        Mencegah Debet dan Kredit memiliki nominal positif
        secara bersamaan pada satu transaksi.
        """

        if self.debet > 0 and self.kredit > 0:
            raise ValueError(
                "Debet dan Kredit tidak boleh "
                "sama-sama bernilai positif."
            )

        return self


# bank statement untuk memvalidasi hasil ekstraksi rekening koran BNI atau BRI.
class BankStatement(BaseModel):
    """
    Hasil ekstraksi satu rekening koran BNI atau BRI.

    Satu rekening koran dapat memiliki banyak transaksi.
    """

    bank: Literal["BNI", "BRI"]

    periode_awal: date | None = None
    periode_akhir: date | None = None

    saldo_awal: Decimal | None = None
    saldo_akhir: Decimal | None = None

    transaksi: list[BankTransaction] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def validate_periode(self):
        """Memastikan periode awal tidak melebihi periode akhir."""

        if (
            self.periode_awal is not None
            and self.periode_akhir is not None
            and self.periode_awal > self.periode_akhir
        ):
            raise ValueError(
                "Periode awal tidak boleh lebih besar "
                "daripada periode akhir."
            )

        return self


# cash report row untuk memvalidasi Cash Report PT Lokal Komoditi Indonesia.
class CashReportRow(BaseModel):
    """
    Satu baris Cash Report PT Lokal Komoditi Indonesia.

    Format mengikuti 10 kolom Cash Report perusahaan.

    Konvensi berdasarkan contoh Cash Report BRI:
    - Debet  = uang masuk
    - Kredit = uang keluar
    - Saldo  = saldo sebelumnya + debet - kredit

    Perlu diverifikasi terhadap Cash Report BNI
    dan transaksi lainnya.
    """

    # 1. Tanggal input dan nama admin
    tanggal_input_dan_nama_admin: str | None = None

    # 2. Tanggal transaksi
    tanggal_transaksi: date | None = None

    # 3. Keterangan transaksi
    keterangan: str | None = None

    # 4. Kategori transaksi
    kategori: str | None = None

    # 5. Keterangan uang masuk
    keterangan_uang_masuk: str | None = None

    # 6. Keterangan uang keluar
    keterangan_uang_keluar: str | None = None

    # 7. Debet (uang masuk)
    debet: Decimal | None = Field(
        default=None,
        ge=0
    )

    # 8. Kredit (uang keluar)
    kredit: Decimal | None = Field(
        default=None,
        ge=0
    )

    # 9. Saldo
    saldo: Decimal | None = None

    # 10. Lampiran nota
    lampiran_nota: str | None = None

    @field_validator(
        "tanggal_input_dan_nama_admin",
        "keterangan",
        "kategori",
        "keterangan_uang_masuk",
        "keterangan_uang_keluar",
        "lampiran_nota",
        mode="before"
    )
    @classmethod
    def clean_text(cls, value):
        """Membersihkan spasi dan mengubah string kosong ke None."""

        if isinstance(value, str):
            return value.strip() or None

        return value

    @model_validator(mode="after")
    def validate_debet_kredit(self):
        """
        Mencegah nominal Debet dan Kredit positif
        secara bersamaan.
        """

        debet = self.debet or Decimal("0")
        kredit = self.kredit or Decimal("0")

        if debet > 0 and kredit > 0:
            raise ValueError(
                "Debet dan Kredit Cash Report tidak boleh "
                "sama-sama bernilai positif."
            )

        return self
