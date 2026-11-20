import calendar

from fastapi import APIRouter, Depends, Query

from app.core.database import get_connection
from app.core.security import require_menu
from app.schemas.auth import UserPublic

router = APIRouter(prefix="/home", tags=["Home"])

PERUSAHAAN = "PT Lokal Komoditi Indonesia"

# Warna kartu rekening di Home (dipilih berdasarkan kode akun).
GRADIENTS = {
    "BNI": "from-[#064E54] via-[#0B6B6F] to-[#0D3B3E]",
    "BRI": "from-[#0A2558] via-[#123D8E] to-[#1D4ED8]",
    "Bank Jago": "from-[#4C1D95] via-[#6D28D9] to-[#2E1065]",
    "Kas Operasional": "from-[#1E293B] via-[#334155] to-[#0F172A]",
}
FALLBACK_GRADIENTS = [
    "from-[#581C87] via-[#7E22CE] to-[#3B0764]",
    "from-[#7C2D12] via-[#C2410C] to-[#431407]",
    "from-[#14532D] via-[#15803D] to-[#052E16]",
]

KELOMPOK_LABEL = {
    "PENGELUARAN": ("Pengeluaran Usaha", "expense"),
    "PEMASUKAN": ("Pemasukan / Lainnya", "income"),
    "NON_USAHA": ("Non-Usaha (Pindah Buku)", "transfer"),
}


def format_rp(amount: float | int) -> str:
    """12345678 -> 'Rp12.345.678' (format Indonesia)."""
    value = int(round(amount or 0))
    sign = "-" if value < 0 else ""
    return f"{sign}Rp{abs(value):,}".replace(",", ".")


BULAN_ID = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]


def _month_range(bulan: str | None) -> tuple[str | None, str | None]:
    """'2026-01' -> ('2026-01-01', '2026-01-31'); None -> (None, None) = semua periode."""
    if not bulan:
        return None, None
    year, month = (int(part) for part in bulan.split("-"))
    last_day = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last_day:02d}"


def _group_key(kode_akun: str) -> str:
    """BRI (BritAma) dan BRI Operasional (BRImo) ditampilkan sebagai satu kartu 'BRI'."""
    kode = (kode_akun or "").strip()
    if kode.upper() == "BRI" or kode.upper().startswith("BRI "):
        return "BRI"
    return kode


def _build_rekening(conn, start: str | None, end: str | None) -> list[dict]:
    accounts = conn.execute(
        """
        SELECT id, kode_akun, bank_lembaga, no_rekening, atas_nama, is_cash
        FROM rekening_perusahaan
        WHERE is_active = 1
        ORDER BY is_cash ASC, id ASC
        """
    ).fetchall()

    # Kelompokkan rekening (urutan dipertahankan).
    groups: dict[str, list] = {}
    for acc in accounts:
        groups.setdefault(_group_key(acc["kode_akun"]), []).append(acc)

    result: list[dict] = []
    for index, (key, members) in enumerate(groups.items()):
        ids = [m["id"] for m in members]
        placeholders = ",".join("?" for _ in ids)
        main = next((m for m in members if m["kode_akun"] == key), members[0])
        is_cash = all(bool(m["is_cash"]) for m in members)

        tx = conn.execute(
            f"""
            SELECT
                COALESCE(SUM(CASE WHEN tipe = 'MASUK' AND rekening_sumber_id IN ({placeholders}) THEN total_mutasi END), 0) AS masuk,
                COALESCE(SUM(CASE WHEN tipe = 'KELUAR' AND rekening_sumber_id IN ({placeholders}) THEN total_mutasi END), 0) AS keluar,
                COALESCE(SUM(CASE WHEN tipe = 'PINDAH_BUKU' AND rekening_sumber_id IN ({placeholders}) THEN total_mutasi END), 0) AS pindah_buku,
                COUNT(*) AS jumlah_struk
            FROM transaksi_internal
            WHERE (rekening_sumber_id IN ({placeholders}) OR rekening_tujuan_id IN ({placeholders}))
              AND (? IS NULL OR tanggal_transaksi >= ?)
              AND (? IS NULL OR tanggal_transaksi <= ?)
            """,
            tuple(ids) * 5 + (start, start, end, end),
        ).fetchone()

        jumlah_mutasi = conn.execute(
            f"""
            SELECT COUNT(*) FROM mutasi_bank
            WHERE rekening_id IN ({placeholders})
              AND (? IS NULL OR tanggal >= ?)
              AND (? IS NULL OR tanggal <= ?)
            """,
            tuple(ids) + (start, start, end, end),
        ).fetchone()[0]

        # Saldo akhir = saldo baris mutasi terakhir tiap rekening sampai akhir periode
        # (atau saldo akhir batch PDF), dijumlah per grup.
        saldo_total = 0.0
        saldo_found = False
        for rek_id in ids:
            last_row = conn.execute(
                """
                SELECT saldo FROM mutasi_bank
                WHERE rekening_id = ? AND saldo IS NOT NULL
                  AND (? IS NULL OR tanggal <= ?)
                ORDER BY tanggal DESC, waktu DESC, id DESC
                LIMIT 1
                """,
                (rek_id, end, end),
            ).fetchone()
            saldo = last_row["saldo"] if last_row else None
            if saldo is None:
                last_batch = conn.execute(
                    """
                    SELECT saldo_akhir_periode FROM mutasi_upload_batch
                    WHERE rekening_id = ? AND saldo_akhir_periode IS NOT NULL
                      AND (? IS NULL OR periode_selesai <= ?)
                    ORDER BY periode_selesai DESC, id DESC
                    LIMIT 1
                    """,
                    (rek_id, end, end),
                ).fetchone()
                saldo = last_batch["saldo_akhir_periode"] if last_batch else None
            if saldo is not None:
                saldo_total += float(saldo)
                saldo_found = True

        if is_cash:
            saldo_akhir_fmt = "Kas Tunai"
        elif saldo_found:
            saldo_akhir_fmt = format_rp(saldo_total)
        else:
            saldo_akhir_fmt = "Belum ada mutasi"

        bank_lembaga = "Bank BRI" if key == "BRI" and len(members) > 1 else main["bank_lembaga"]
        no_rekening = ", ".join(m["no_rekening"] for m in members if m["no_rekening"] and m["no_rekening"] != "-")
        atas_nama = " / ".join(dict.fromkeys(m["atas_nama"] for m in members if m["atas_nama"]))

        result.append(
            {
                "nama_akun": key,
                "bank_lembaga": bank_lembaga,
                "no_rekening": no_rekening or main["no_rekening"],
                "atas_nama": atas_nama or main["atas_nama"],
                "saldo_akhir_fmt": saldo_akhir_fmt,
                "masuk_fmt": format_rp(tx["masuk"]),
                "keluar_fmt": format_rp(tx["keluar"]),
                "pindah_buku_fmt": format_rp(tx["pindah_buku"]),
                "jumlah_struk": tx["jumlah_struk"],
                "jumlah_mutasi": jumlah_mutasi,
                "has_mutasi": jumlah_mutasi > 0,
                "gradient": GRADIENTS.get(key, FALLBACK_GRADIENTS[index % len(FALLBACK_GRADIENTS)]),
            }
        )
    return result


def _build_kategori(conn, start: str | None, end: str | None) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            ks.no_urut,
            ks.nama_kategori,
            ks.kelompok,
            COALESCE(SUM(ti.total_mutasi), 0) AS total_nominal,
            COUNT(ti.id) AS jumlah_transaksi
        FROM kategori_sop ks
        LEFT JOIN transaksi_internal ti
            ON ti.kategori_id = ks.id
           AND (? IS NULL OR ti.tanggal_transaksi >= ?)
           AND (? IS NULL OR ti.tanggal_transaksi <= ?)
        WHERE ks.is_active = 1
        GROUP BY ks.id
        ORDER BY ks.no_urut ASC
        """,
        (start, start, end, end),
    ).fetchall()

    result: list[dict] = []
    for row in rows:
        kelompok_label, badge = KELOMPOK_LABEL.get(row["kelompok"], (row["kelompok"], "transfer"))
        total = int(round(row["total_nominal"] or 0))
        result.append(
            {
                "no": row["no_urut"],
                "nama": row["nama_kategori"],
                "kelompok": kelompok_label,
                "badge": badge,
                "total_nominal": total,
                "total_nominal_fmt": format_rp(total),
                "jumlah_transaksi": row["jumlah_transaksi"],
            }
        )
    return result


def build_home_data(bulan: str | None = None) -> dict:
    """Ringkasan Home dihitung langsung dari SQLite (transaksi_internal & mutasi_bank).

    bulan = 'YYYY-MM' untuk satu bulan; None = semua periode.
    """
    start, end = _month_range(bulan)
    if bulan:
        year, month = (int(part) for part in bulan.split("-"))
        periode_label = f"{BULAN_ID[month - 1]} {year}"
    else:
        periode_label = "Semua Periode"
    with get_connection() as conn:
        return {
            "perusahaan": PERUSAHAAN,
            "bulan": bulan,
            "periode_label": periode_label,
            "rekening": _build_rekening(conn, start, end),
            "kategori": _build_kategori(conn, start, end),
        }


@router.get("")
def get_home(
    bulan: str | None = Query(
        None,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="Filter bulan format YYYY-MM, mis. 2026-01. Kosong = semua periode.",
    ),
    _: UserPublic = Depends(require_menu("home")),
) -> dict:
    """Data halaman Home dari database (akses dicek di tabel role_menus SQLite)."""
    return build_home_data(bulan)
