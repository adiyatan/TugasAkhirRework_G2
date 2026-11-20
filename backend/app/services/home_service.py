from __future__ import annotations

from contextlib import closing

from app.core.database import get_connection
from app.services.rekonsiliasi_service import COMPANY_NAME, _sort_mutasi_chronological

ACCOUNT_GRADIENTS: dict[str, str] = {
    "BNI": "from-[#064E54] via-[#0B6B6F] to-[#0D3B3E]",
    "BRI": "from-[#0A2558] via-[#123D8E] to-[#1D4ED8]",
    "BRI Operasional": "from-[#0F4C81] via-[#1D4ED8] to-[#1E3A8A]",
    "Bank Jago": "from-[#4C1D95] via-[#6D28D9] to-[#2E1065]",
    "Kas Operasional": "from-[#1E293B] via-[#334155] to-[#0F172A]",
}

FALLBACK_GRADIENTS: tuple[str, ...] = (
    "from-[#064E54] via-[#0B6B6F] to-[#0D3B3E]",
    "from-[#0A2558] via-[#123D8E] to-[#1D4ED8]",
    "from-[#0F4C81] via-[#1D4ED8] to-[#1E3A8A]",
    "from-[#4C1D95] via-[#6D28D9] to-[#2E1065]",
    "from-[#1E293B] via-[#334155] to-[#0F172A]",
)

KELOMPOK_META: dict[str, tuple[str, str]] = {
    "PENGELUARAN": ("Pengeluaran Usaha", "expense"),
    "PEMASUKAN": ("Pemasukan / Lainnya", "income"),
    "NON_USAHA": ("Non-Usaha (Pindah Buku)", "transfer"),
}


def format_rp(amount: float | int) -> str:
    """Format nominal Rupiah dengan pemisah ribuan titik."""
    value = int(round(float(amount)))
    sign = "-" if value < 0 else ""
    return f"{sign}Rp{abs(value):,}".replace(",", ".")


class HomeService:
    """Menyusun ringkasan rekening dan kategori SOP menu Home dari database SQLite."""

    def get_home_data(self) -> dict:
        with closing(get_connection()) as conn:
            accounts = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT id, kode_akun, bank_lembaga, no_rekening, atas_nama, peran, is_cash
                    FROM rekening_perusahaan
                    WHERE is_active = 1
                    ORDER BY is_cash ASC, id ASC
                    """
                ).fetchall()
            ]
            categories = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT id, no_urut, nama_kategori, kelompok
                    FROM kategori_sop
                    WHERE is_active = 1
                    ORDER BY no_urut ASC, id ASC
                    """
                ).fetchall()
            ]
            tx_rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT id, tipe, rekening_sumber_id, rekening_tujuan_id,
                           kategori_id, nominal_pokok, total_mutasi
                    FROM transaksi_internal
                    """
                ).fetchall()
            ]
            mutasi_rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT id, rekening_id, tanggal, waktu, tipe, nominal, saldo
                    FROM mutasi_bank
                    ORDER BY tanggal ASC, waktu ASC, id ASC
                    """
                ).fetchall()
            ]
            batch_rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT rekening_id, saldo_akhir_periode
                    FROM mutasi_upload_batch
                    ORDER BY periode_selesai DESC, id DESC
                    """
                ).fetchall()
            ]

        account_stats: dict[int, dict[str, float | int]] = {
            int(acc["id"]): {"masuk": 0.0, "keluar": 0.0, "pindah_buku": 0.0, "jumlah_struk": 0}
            for acc in accounts
        }
        category_stats: dict[int, dict[str, float | int]] = {
            int(cat["id"]): {"total_nominal": 0.0, "jumlah_transaksi": 0}
            for cat in categories
        }
        summary_totals = {
            "masuk": 0.0,
            "masuk_count": 0,
            "keluar": 0.0,
            "keluar_count": 0,
            "pindah_buku": 0.0,
            "pindah_buku_count": 0,
        }

        for tx in tx_rows:
            total = float(tx["total_mutasi"] or 0)
            pokok = float(tx["nominal_pokok"] or 0)
            kat_id = int(tx["kategori_id"])
            if kat_id in category_stats:
                category_stats[kat_id]["total_nominal"] += total
                category_stats[kat_id]["jumlah_transaksi"] += 1

            sumber_id = int(tx["rekening_sumber_id"])
            tujuan_id = int(tx["rekening_tujuan_id"]) if tx["rekening_tujuan_id"] is not None else None
            tipe = tx["tipe"]

            if tipe == "MASUK":
                summary_totals["masuk"] += total
                summary_totals["masuk_count"] += 1
                if sumber_id in account_stats:
                    account_stats[sumber_id]["masuk"] += total
                    account_stats[sumber_id]["jumlah_struk"] += 1
            elif tipe == "KELUAR":
                summary_totals["keluar"] += total
                summary_totals["keluar_count"] += 1
                if sumber_id in account_stats:
                    account_stats[sumber_id]["keluar"] += total
                    account_stats[sumber_id]["jumlah_struk"] += 1
            elif tipe == "PINDAH_BUKU":
                summary_totals["pindah_buku"] += total
                summary_totals["pindah_buku_count"] += 1
                if sumber_id in account_stats:
                    account_stats[sumber_id]["pindah_buku"] += total
                    account_stats[sumber_id]["jumlah_struk"] += 1
                if tujuan_id is not None and tujuan_id != sumber_id and tujuan_id in account_stats:
                    account_stats[tujuan_id]["pindah_buku"] += pokok if pokok > 0 else total
                    account_stats[tujuan_id]["jumlah_struk"] += 1

        mutasi_by_account: dict[int, list[dict]] = {}
        for row in mutasi_rows:
            mutasi_by_account.setdefault(int(row["rekening_id"]), []).append(row)

        batch_saldo_by_account: dict[int, float | None] = {}
        for batch in batch_rows:
            rid = int(batch["rekening_id"])
            if rid not in batch_saldo_by_account and batch["saldo_akhir_periode"] is not None:
                batch_saldo_by_account[rid] = float(batch["saldo_akhir_periode"])

        rekening_payload: list[dict] = []
        for idx, acc in enumerate(accounts):
            aid = int(acc["id"])
            stats = account_stats[aid]
            acc_mutasi = mutasi_by_account.get(aid, [])
            jumlah_mutasi = len(acc_mutasi)
            has_mutasi = jumlah_mutasi > 0

            saldo_akhir: float | None = None
            if has_mutasi:
                ordered = _sort_mutasi_chronological(acc_mutasi)
                for row in reversed(ordered):
                    if row.get("saldo") is not None:
                        saldo_akhir = float(row["saldo"])
                        break
                if saldo_akhir is None:
                    saldo_akhir = batch_saldo_by_account.get(aid)

            if saldo_akhir is not None:
                saldo_akhir_fmt = format_rp(saldo_akhir)
            elif acc["is_cash"]:
                saldo_akhir_fmt = "Kas Tunai"
            elif has_mutasi:
                saldo_akhir_fmt = "Tercatat di mutasi"
            else:
                saldo_akhir_fmt = "Belum ada mutasi"

            rekening_payload.append(
                {
                    "id": aid,
                    "nama_akun": acc["kode_akun"],
                    "bank_lembaga": acc["bank_lembaga"],
                    "no_rekening": acc["no_rekening"],
                    "atas_nama": acc["atas_nama"],
                    "peran": acc["peran"],
                    "is_cash": bool(acc["is_cash"]),
                    "saldo_akhir": int(round(saldo_akhir)) if saldo_akhir is not None else None,
                    "saldo_akhir_fmt": saldo_akhir_fmt,
                    "masuk_fmt": format_rp(stats["masuk"]),
                    "keluar_fmt": format_rp(stats["keluar"]),
                    "pindah_buku_fmt": format_rp(stats["pindah_buku"]),
                    "jumlah_struk": int(stats["jumlah_struk"]),
                    "jumlah_mutasi": jumlah_mutasi,
                    "has_mutasi": has_mutasi,
                    "gradient": ACCOUNT_GRADIENTS.get(
                        acc["kode_akun"],
                        FALLBACK_GRADIENTS[idx % len(FALLBACK_GRADIENTS)],
                    ),
                }
            )

        kategori_payload: list[dict] = []
        for cat in categories:
            cid = int(cat["id"])
            cstats = category_stats[cid]
            kelompok_label, badge = KELOMPOK_META.get(
                cat["kelompok"],
                ("Non-Usaha (Pindah Buku)", "transfer"),
            )
            total_nominal = int(round(float(cstats["total_nominal"])))
            kategori_payload.append(
                {
                    "id": cid,
                    "no": int(cat["no_urut"]),
                    "nama": cat["nama_kategori"],
                    "kelompok": kelompok_label,
                    "badge": badge,
                    "total_nominal": total_nominal,
                    "total_nominal_fmt": format_rp(total_nominal),
                    "jumlah_transaksi": int(cstats["jumlah_transaksi"]),
                }
            )

        total_pemasukan = int(round(summary_totals["masuk"]))
        total_pengeluaran = int(round(summary_totals["keluar"]))
        selisih_bersih = total_pemasukan - total_pengeluaran
        total_pindah = int(round(summary_totals["pindah_buku"]))

        return {
            "perusahaan": COMPANY_NAME,
            "rekening": rekening_payload,
            "kategori": kategori_payload,
            "ringkasan": {
                "total_pemasukan": total_pemasukan,
                "total_pemasukan_fmt": format_rp(total_pemasukan),
                "jumlah_pemasukan": int(summary_totals["masuk_count"]),
                "total_pengeluaran": total_pengeluaran,
                "total_pengeluaran_fmt": format_rp(total_pengeluaran),
                "jumlah_pengeluaran": int(summary_totals["keluar_count"]),
                "selisih_bersih": selisih_bersih,
                "selisih_bersih_fmt": format_rp(selisih_bersih),
                "total_pindah_buku": total_pindah,
                "total_pindah_buku_fmt": format_rp(total_pindah),
                "jumlah_pindah_buku": int(summary_totals["pindah_buku_count"]),
            },
        }


home_service = HomeService()
