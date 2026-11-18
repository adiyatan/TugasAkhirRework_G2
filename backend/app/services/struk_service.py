from __future__ import annotations

from app.core.database import get_connection
from app.schemas.struk import StrukMetadata


class StrukService:
    """Business logic for the Input Struk workflow."""

    def get_metadata(self) -> StrukMetadata:
        with get_connection() as conn:
            rekening_rows = conn.execute(
                """
                SELECT id, kode_akun, bank_lembaga, no_rekening, atas_nama, peran, is_cash
                FROM rekening_perusahaan
                WHERE is_active = 1
                ORDER BY is_cash ASC, id ASC
                """
            ).fetchall()
            kategori_rows = conn.execute(
                """
                SELECT id, no_urut, nama_kategori, kelompok
                FROM kategori_sop
                WHERE is_active = 1
                ORDER BY no_urut ASC
                """
            ).fetchall()
            excluded_rows = conn.execute(
                """
                SELECT id, nama_pemilik, potongan_no_rek, keterangan
                FROM rekening_dikecualikan
                WHERE is_active = 1
                ORDER BY id ASC
                """
            ).fetchall()

        return StrukMetadata(
            rekening_perusahaan=[
                {
                    **dict(row),
                    "is_cash": bool(row["is_cash"]),
                }
                for row in rekening_rows
            ],
            kategori_sop=[dict(row) for row in kategori_rows],
            rekening_dikecualikan=[dict(row) for row in excluded_rows],
            tabs=["normal", "flip", "slip_gaji", "reimburse"],
        )


struk_service = StrukService()
