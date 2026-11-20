from __future__ import annotations

import calendar
from datetime import date, timedelta
from itertools import permutations
import re
import sqlite3
import uuid

from app.core.database import get_connection
from app.schemas.auth import UserPublic
from app.schemas.rekonsiliasi import RekonPenyesuaianRequest

DATE_WINDOW_DAYS = 2
TOLERANCE_RUPIAH = 1000


def _date_bounds(tanggal_transaksi: str) -> tuple[str, str] | None:
    try:
        center = date.fromisoformat(tanggal_transaksi)
    except ValueError:
        return None
    start = (center - timedelta(days=DATE_WINDOW_DAYS)).isoformat()
    end = (center + timedelta(days=DATE_WINDOW_DAYS)).isoformat()
    return start, end


def _pick_best_candidate(
    conn: sqlite3.Connection,
    *,
    rekening_id: int,
    mutasi_tipe: str,
    target_amount: float,
    target_date: str,
    start_date: str,
    end_date: str,
    max_diff: float,
) -> sqlite3.Row | None:
    """Find the closest unmatched mutasi_bank row within date and amount tolerance."""
    return conn.execute(
        """
        SELECT id, tanggal, nominal, ABS(nominal - ?) AS diff_amount
        FROM mutasi_bank
        WHERE rekening_id = ?
          AND tipe = ?
          AND status_rekonsiliasi IN ('BELUM_REKON', 'BELUM_TERCATAT')
          AND tanggal BETWEEN ? AND ?
          AND ABS(nominal - ?) <= ?
        ORDER BY
          CASE WHEN ABS(nominal - ?) < 1 THEN 0 ELSE 1 END ASC,
          CASE WHEN tanggal = ? THEN 0 ELSE 1 END ASC,
          ABS(julianday(tanggal) - julianday(?)) ASC,
          diff_amount ASC,
          id ASC
        LIMIT 1
        """,
        (
            target_amount,
            rekening_id,
            mutasi_tipe,
            start_date,
            end_date,
            target_amount,
            max_diff,
            target_amount,
            target_date,
            target_date,
        ),
    ).fetchone()


def auto_reconcile_transaction(transaksi_id: int) -> dict:
    """Try matching one newly saved transaksi_internal row against existing mutasi_bank."""
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        tx = conn.execute(
            """
            SELECT ti.id, ti.tanggal_transaksi, ti.rekening_sumber_id, ti.rekening_tujuan_id,
                   ti.tipe, ti.nominal_pokok, ti.total_mutasi, ti.status_rekonsiliasi,
                   rs.is_cash AS sumber_is_cash
            FROM transaksi_internal ti
            JOIN rekening_perusahaan rs ON rs.id = ti.rekening_sumber_id
            WHERE ti.id = ?
            """,
            (transaksi_id,),
        ).fetchone()

        if not tx:
            conn.rollback()
            return {"matched": False, "status_rekonsiliasi": "BELUM_REKON", "jenis_match": None}

        if tx["status_rekonsiliasi"] not in {"BELUM_REKON", "MUTASI_BELUM_ADA"} or tx["sumber_is_cash"]:
            conn.commit()
            return {
                "matched": False,
                "status_rekonsiliasi": tx["status_rekonsiliasi"],
                "jenis_match": None,
            }

        bounds = _date_bounds(tx["tanggal_transaksi"])
        if not bounds:
            conn.commit()
            return {"matched": False, "status_rekonsiliasi": "BELUM_REKON", "jenis_match": None}
        start_date, end_date = bounds

        if tx["tipe"] == "PINDAH_BUKU":
            if not tx["rekening_tujuan_id"]:
                conn.commit()
                return {"matched": False, "status_rekonsiliasi": "BELUM_REKON", "jenis_match": None}

            out_mutasi = _pick_best_candidate(
                conn,
                rekening_id=tx["rekening_sumber_id"],
                mutasi_tipe="DB",
                target_amount=tx["total_mutasi"],
                target_date=tx["tanggal_transaksi"],
                start_date=start_date,
                end_date=end_date,
                max_diff=TOLERANCE_RUPIAH,
            )
            in_target = tx["nominal_pokok"] if tx["nominal_pokok"] > 0 else tx["total_mutasi"]
            in_mutasi = _pick_best_candidate(
                conn,
                rekening_id=tx["rekening_tujuan_id"],
                mutasi_tipe="CR",
                target_amount=in_target,
                target_date=tx["tanggal_transaksi"],
                start_date=start_date,
                end_date=end_date,
                max_diff=TOLERANCE_RUPIAH,
            )
            if not out_mutasi or not in_mutasi:
                conn.commit()
                return {"matched": False, "status_rekonsiliasi": "BELUM_REKON", "jenis_match": None}

            group_id = f"grp_{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO rekonsiliasi_match (
                    match_group_id, transaksi_internal_id, mutasi_bank_id,
                    jenis_match, peran_mutasi, selisih_nominal, is_manual, catatan
                ) VALUES (?, ?, ?, 'PINDAH_BUKU_PAIR', 'PINDAH_KELUAR', ?, 0, 'Auto rekon saat simpan struk')
                """,
                (group_id, transaksi_id, out_mutasi["id"], out_mutasi["nominal"] - tx["total_mutasi"]),
            )
            conn.execute(
                """
                INSERT INTO rekonsiliasi_match (
                    match_group_id, transaksi_internal_id, mutasi_bank_id,
                    jenis_match, peran_mutasi, selisih_nominal, is_manual, catatan
                ) VALUES (?, ?, ?, 'PINDAH_BUKU_PAIR', 'PINDAH_MASUK', ?, 0, 'Auto rekon saat simpan struk')
                """,
                (group_id, transaksi_id, in_mutasi["id"], in_mutasi["nominal"] - in_target),
            )
            conn.execute(
                "UPDATE transaksi_internal SET status_rekonsiliasi = 'PINDAH_BUKU_COCOK' WHERE id = ?",
                (transaksi_id,),
            )
            conn.execute(
                "UPDATE mutasi_bank SET status_rekonsiliasi = 'PINDAH_BUKU' WHERE id IN (?, ?)",
                (out_mutasi["id"], in_mutasi["id"]),
            )
            conn.commit()
            return {
                "matched": True,
                "status_rekonsiliasi": "PINDAH_BUKU_COCOK",
                "jenis_match": "PINDAH_BUKU_PAIR",
                "mutasi_ids": [out_mutasi["id"], in_mutasi["id"]],
            }

        mutasi_tipe = "CR" if tx["tipe"] == "MASUK" else "DB"
        candidate = _pick_best_candidate(
            conn,
            rekening_id=tx["rekening_sumber_id"],
            mutasi_tipe=mutasi_tipe,
            target_amount=tx["total_mutasi"],
            target_date=tx["tanggal_transaksi"],
            start_date=start_date,
            end_date=end_date,
            max_diff=TOLERANCE_RUPIAH,
        )
        if not candidate:
            conn.commit()
            return {"matched": False, "status_rekonsiliasi": "BELUM_REKON", "jenis_match": None}

        diff = candidate["nominal"] - tx["total_mutasi"]
        is_exact = abs(diff) < 1
        jenis_match = "EXACT" if is_exact else "TOLERANCE"
        tx_status = "SESUAI" if is_exact else "SELISIH_KODE_UNIK_ADMIN"
        group_id = f"grp_{uuid.uuid4().hex[:12]}"

        conn.execute(
            """
            INSERT INTO rekonsiliasi_match (
                match_group_id, transaksi_internal_id, mutasi_bank_id,
                jenis_match, peran_mutasi, selisih_nominal, is_manual, catatan
            ) VALUES (?, ?, ?, ?, 'UTAMA', ?, 0, 'Auto rekon saat simpan struk')
            """,
            (group_id, transaksi_id, candidate["id"], jenis_match, 0 if is_exact else diff),
        )
        conn.execute(
            "UPDATE transaksi_internal SET status_rekonsiliasi = ? WHERE id = ?",
            (tx_status, transaksi_id),
        )
        conn.execute(
            "UPDATE mutasi_bank SET status_rekonsiliasi = ? WHERE id = ?",
            (tx_status, candidate["id"]),
        )
        conn.commit()
        return {
            "matched": True,
            "status_rekonsiliasi": tx_status,
            "jenis_match": jenis_match,
            "mutasi_ids": [candidate["id"]],
        }


def unlink_reconciliation_for_transaction(conn: sqlite3.Connection, transaksi_id: int) -> None:
    """Reset mutasi_bank rows linked solely to this transaction before deleting it."""
    rows = conn.execute(
        "SELECT mutasi_bank_id FROM rekonsiliasi_match WHERE transaksi_internal_id = ?",
        (transaksi_id,),
    ).fetchall()
    mutasi_ids = [row["mutasi_bank_id"] for row in rows]
    conn.execute("DELETE FROM rekonsiliasi_match WHERE transaksi_internal_id = ?", (transaksi_id,))
    for mutasi_id in mutasi_ids:
        remaining = conn.execute(
            "SELECT 1 FROM rekonsiliasi_match WHERE mutasi_bank_id = ? LIMIT 1",
            (mutasi_id,),
        ).fetchone()
        if not remaining:
            conn.execute(
                "UPDATE mutasi_bank SET status_rekonsiliasi = 'BELUM_REKON' WHERE id = ?",
                (mutasi_id,),
            )


BANK_FEE_KEYWORDS = (
    "INTEREST",
    "BUNGA",
    "TAX",
    "PAJAK",
    "ADMIN REKENING",
    "BIAYA ADM",
    "BIAYA TRANSFER",
    "MATERAI",
)


def _classify_unmatched_mutasi_reason(uraian: str) -> str:
    upper = uraian.upper()
    if any(kw in upper for kw in BANK_FEE_KEYWORDS):
        return "Biaya Administrasi / Bunga / Pajak Bank"
    return ""


def auto_reconcile_mutasi_batch(batch_id: int) -> dict:
    """Reconcile existing transaksi_internal against a newly saved mutasi batch."""
    with get_connection() as conn:
        batch = conn.execute(
            "SELECT id, rekening_id, periode_mulai, periode_selesai FROM mutasi_upload_batch WHERE id = ?",
            (batch_id,),
        ).fetchone()
        if not batch:
            return {"matched_transactions": 0, "unmatched_mutasi": 0}
        tx_rows = conn.execute(
            """
            SELECT id FROM transaksi_internal
            WHERE status_rekonsiliasi IN ('BELUM_REKON', 'MUTASI_BELUM_ADA')
              AND (rekening_sumber_id = ? OR rekening_tujuan_id = ?)
            ORDER BY tanggal_transaksi ASC, id ASC
            """,
            (batch["rekening_id"], batch["rekening_id"]),
        ).fetchall()

    matched_transactions = 0
    for row in tx_rows:
        result = auto_reconcile_transaction(row["id"])
        if result.get("matched"):
            matched_transactions += 1

    with get_connection() as conn:
        unmatched_rows = conn.execute(
            """
            SELECT id, uraian FROM mutasi_bank
            WHERE batch_id = ? AND status_rekonsiliasi = 'BELUM_REKON'
            """,
            (batch_id,),
        ).fetchall()
        for mut in unmatched_rows:
            reason = _classify_unmatched_mutasi_reason(mut["uraian"])
            conn.execute(
                """
                UPDATE mutasi_bank
                SET status_rekonsiliasi = 'BELUM_TERCATAT',
                    penyebab_selisih = CASE WHEN penyebab_selisih = '' THEN ? ELSE penyebab_selisih END
                WHERE id = ?
                """,
                (reason, mut["id"]),
            )
        conn.commit()

    return {
        "matched_transactions": matched_transactions,
        "unmatched_mutasi": len(unmatched_rows),
    }


def recalculate_reconciliation_for_transactions(tx_ids: list[int]) -> dict:
    """Reset and re-evaluate transactions whose matched mutasi batch was removed."""
    unique_ids = sorted(set(tx_ids))
    if not unique_ids:
        return {"recalculated": 0, "rematched": 0}

    with get_connection() as conn:
        for tx_id in unique_ids:
            remaining = conn.execute(
                "SELECT 1 FROM rekonsiliasi_match WHERE transaksi_internal_id = ? LIMIT 1",
                (tx_id,),
            ).fetchone()
            if not remaining:
                conn.execute(
                    "UPDATE transaksi_internal SET status_rekonsiliasi = 'BELUM_REKON' WHERE id = ?",
                    (tx_id,),
                )
        conn.commit()

    rematched = 0
    for tx_id in unique_ids:
        if auto_reconcile_transaction(tx_id).get("matched"):
            rematched += 1
    return {"recalculated": len(unique_ids), "rematched": rematched}


COMPANY_NAME = "PT Lokal Komoditi Indonesia"
BULAN_ID = (
    "Januari",
    "Februari",
    "Maret",
    "April",
    "Mei",
    "Juni",
    "Juli",
    "Agustus",
    "September",
    "Oktober",
    "November",
    "Desember",
)


class RekonError(Exception):
    """Domain error for reconciliation and Cash Report operations."""

    status_code = 400

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


def _round2(value: float | int) -> float:
    rounded = round(float(value), 2)
    return 0.0 if abs(rounded) < 0.005 else rounded


def _parse_month(month: str) -> tuple[int, int, str, str]:
    match = re.fullmatch(r"(\d{4})-(\d{2})", str(month or "").strip())
    if not match:
        raise RekonError("Format bulan wajib YYYY-MM")
    year, month_num = int(match.group(1)), int(match.group(2))
    if month_num < 1 or month_num > 12:
        raise RekonError("Bulan harus antara 01 dan 12")
    last_day = calendar.monthrange(year, month_num)[1]
    start = f"{year:04d}-{month_num:02d}-01"
    end = f"{year:04d}-{month_num:02d}-{last_day:02d}"
    return year, month_num, start, end


def _month_label(year: int, month_num: int) -> str:
    return f"{BULAN_ID[month_num - 1]} {year}"


def _format_tanggal_id(iso_date: str) -> str:
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(iso_date or ""))
    if not match:
        return str(iso_date or "")
    y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
    if m < 1 or m > 12:
        return str(iso_date or "")
    return f"{d} {BULAN_ID[m - 1]} {y}"


def _months_between(start_iso: str, end_iso: str) -> list[str]:
    m_start = re.match(r"^(\d{4})-(\d{2})", str(start_iso or ""))
    m_end = re.match(r"^(\d{4})-(\d{2})", str(end_iso or ""))
    if not m_start or not m_end:
        return []
    y, m = int(m_start.group(1)), int(m_start.group(2))
    end_y, end_m = int(m_end.group(1)), int(m_end.group(2))
    if not (1 <= m <= 12 and 1 <= end_m <= 12) or (y, m) > (end_y, end_m):
        return []
    result: list[str] = []
    while (y, m) <= (end_y, end_m) and len(result) < 120:
        result.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return result


def _delta(row: dict) -> float:
    nominal = float(row["nominal"])
    return nominal if row["tipe"] == "CR" else -nominal


def _chain_valid(prev_saldo: float | None, seq: tuple[dict, ...] | list[dict]) -> bool:
    running = prev_saldo
    for idx, row in enumerate(seq):
        if row.get("saldo") is None:
            return False
        if idx == 0 and running is None:
            running = float(row["saldo"])
            continue
        assert running is not None
        expected = running + _delta(row)
        if abs(expected - float(row["saldo"])) > 0.01:
            return False
        running = float(row["saldo"])
    return True


def _sort_mutasi_chronological(rows: list[dict], *, initial_saldo: float | None = None) -> list[dict]:
    """Sort mutasi rows chronologically, resolving equal (tanggal, waktu) ties via running saldo."""
    if len(rows) <= 1:
        return list(rows)
    ordered = sorted(rows, key=lambda r: (r["tanggal"], r["waktu"] or "00:00:00", int(r["id"])))
    result: list[dict] = []
    idx = 0
    prev_saldo = initial_saldo

    while idx < len(ordered):
        key = (ordered[idx]["tanggal"], ordered[idx]["waktu"] or "00:00:00")
        end = idx + 1
        while end < len(ordered) and (ordered[end]["tanggal"], ordered[end]["waktu"] or "00:00:00") == key:
            end += 1
        group = ordered[idx:end]
        if len(group) > 1 and all(r.get("saldo") is not None for r in group):
            if _chain_valid(prev_saldo, group):
                chosen = group
            elif _chain_valid(prev_saldo, list(reversed(group))):
                chosen = list(reversed(group))
            elif len(group) <= 5:
                chosen = group
                for perm in permutations(group):
                    if _chain_valid(prev_saldo, perm):
                        chosen = list(perm)
                        break
            else:
                chosen = group
        else:
            chosen = group
        result.extend(chosen)
        if chosen[-1].get("saldo") is not None:
            prev_saldo = float(chosen[-1]["saldo"])
        idx = end

    return result


def _build_keterangan(tx: dict) -> str:
    ket = str(tx.get("keterangan") or "").strip()
    pihak = str(tx.get("penerima_pengirim") or "").strip()
    if not ket:
        return pihak or "-"
    if pihak and pihak.lower() not in ket.lower():
        return f"{ket} - {pihak}"
    return ket


def _map_tx_to_cash_report_row(tx: dict, rekening_id: int, files: list[dict], matches: list[dict]) -> dict | None:
    """Map one transaksi_internal row to Cash Report row following REQUIREMENT_INPUT_STRUK.md."""
    sumber_id = int(tx["rekening_sumber_id"])
    tujuan_id = int(tx["rekening_tujuan_id"]) if tx.get("rekening_tujuan_id") is not None else None
    tipe = tx["tipe"]
    total = _round2(tx["total_mutasi"])
    pokok = _round2(tx["nominal_pokok"])
    masuk_pb = pokok if pokok > 0 else total

    if tipe == "MASUK" and sumber_id == rekening_id:
        uang_masuk = tx["rekening_sumber"]
        uang_keluar = ""
        debet = total
        kredit = 0.0
    elif tipe == "KELUAR" and sumber_id == rekening_id:
        uang_masuk = ""
        uang_keluar = tx["rekening_sumber"]
        debet = 0.0
        kredit = total
    elif tipe == "PINDAH_BUKU" and sumber_id == rekening_id:
        uang_masuk = tx.get("rekening_tujuan") or ""
        uang_keluar = tx["rekening_sumber"]
        debet = 0.0
        kredit = total
    elif tipe == "PINDAH_BUKU" and tujuan_id == rekening_id:
        uang_masuk = tx.get("rekening_tujuan") or ""
        uang_keluar = tx["rekening_sumber"]
        debet = masuk_pb
        kredit = 0.0
    else:
        return None

    admin_parts = [
        _format_tanggal_id(tx["tanggal_input"]),
        str(tx.get("nama_admin") or "").strip(),
    ]
    tanggal_input_admin = " - ".join(p for p in admin_parts if p)

    if files:
        names = ", ".join(f["orig_filename"] for f in files)
        lampiran = f"Terlampir ({names})"
    elif tx.get("sumber_pencatatan") == "PENYESUAIAN_MUTASI":
        lampiran = "Penyesuaian Mutasi"
    else:
        lampiran = "Belum Terlampir"

    return {
        "id": int(tx["id"]),
        "sumber_pencatatan": tx.get("sumber_pencatatan") or "INPUT_STRUK",
        "tab_type": tx.get("tab_type") or "normal",
        "tipe": tipe,
        "tanggal_input": tx["tanggal_input"],
        "nama_admin": tx.get("nama_admin") or "",
        "tanggal_input_admin": tanggal_input_admin,
        "tanggal_transaksi": tx["tanggal_transaksi"],
        "waktu_transaksi": tx.get("waktu_transaksi") or "12:00:00",
        "keterangan": _build_keterangan(tx),
        "penerima_pengirim": tx.get("penerima_pengirim") or "",
        "kategori": tx.get("nama_kategori") or "-",
        "kategori_id": int(tx["kategori_id"]),
        "rekening_sumber_id": sumber_id,
        "rekening_sumber": tx["rekening_sumber"],
        "rekening_tujuan_id": tujuan_id,
        "rekening_tujuan": tx.get("rekening_tujuan"),
        "uang_masuk": uang_masuk,
        "uang_keluar": uang_keluar,
        "debet": debet,
        "kredit": kredit,
        "nominal_pokok": pokok,
        "biaya_admin_kode_unik": _round2(tx.get("biaya_admin_kode_unik") or 0),
        "total_mutasi": total,
        "lampiran": lampiran,
        "files": files,
        "status_rekonsiliasi": tx.get("status_rekonsiliasi") or "BELUM_REKON",
        "catatan_rekonsiliasi": tx.get("catatan_rekonsiliasi") or "",
        "matches": matches,
    }


def _sanitize_filename_part(raw: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", raw).strip("_") or "Rekening"


class RekonsiliasiService:
    """Business logic for menu Rekonsiliasi, Cash Report, manual matching, and adjustment."""

    def get_metadata(self) -> dict:
        today = date.today()
        months = {f"{today.year:04d}-{m:02d}" for m in range(1, today.month + 1)}

        with get_connection() as conn:
            accounts = [
                {**dict(row), "is_cash": bool(row["is_cash"])}
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
                    ORDER BY no_urut ASC
                    """
                ).fetchall()
            ]
            tx_rows = conn.execute(
                """
                SELECT rekening_sumber_id, rekening_tujuan_id, tipe, substr(tanggal_transaksi, 1, 7) AS ym
                FROM transaksi_internal
                """
            ).fetchall()
            mutasi_rows = conn.execute(
                """
                SELECT rekening_id, substr(tanggal, 1, 7) AS ym
                FROM mutasi_bank
                """
            ).fetchall()
            batches = conn.execute(
                """
                SELECT rekening_id, periode_mulai, periode_selesai
                FROM mutasi_upload_batch
                """
            ).fetchall()

        tx_counts: dict[int, dict[str, int]] = {a["id"]: {} for a in accounts}
        mutasi_counts: dict[int, dict[str, int]] = {a["id"]: {} for a in accounts}

        for row in tx_rows:
            ym = row["ym"]
            if not ym or len(ym) != 7:
                continue
            months.add(ym)
            s_id = int(row["rekening_sumber_id"])
            if s_id in tx_counts:
                tx_counts[s_id][ym] = tx_counts[s_id].get(ym, 0) + 1
            if row["tipe"] == "PINDAH_BUKU" and row["rekening_tujuan_id"] is not None:
                t_id = int(row["rekening_tujuan_id"])
                if t_id != s_id and t_id in tx_counts:
                    tx_counts[t_id][ym] = tx_counts[t_id].get(ym, 0) + 1

        for row in mutasi_rows:
            ym = row["ym"]
            if not ym or len(ym) != 7:
                continue
            months.add(ym)
            r_id = int(row["rekening_id"])
            if r_id in mutasi_counts:
                mutasi_counts[r_id][ym] = mutasi_counts[r_id].get(ym, 0) + 1

        for b in batches:
            for ym in _months_between(b["periode_mulai"], b["periode_selesai"]):
                months.add(ym)

        sorted_months = sorted(months, reverse=True)
        activity = {}
        for acc in accounts:
            aid = acc["id"]
            tx_m = tx_counts.get(aid, {})
            mut_m = mutasi_counts.get(aid, {})
            all_ym = set(tx_m) | set(mut_m)
            activity[str(aid)] = {
                "tx_total": sum(tx_m.values()),
                "mutasi_total": sum(mut_m.values()),
                "tx_per_month": tx_m,
                "mutasi_per_month": mut_m,
                "latest_month": max(all_ym) if all_ym else (sorted_months[0] if sorted_months else None),
            }

        return {
            "rekening_perusahaan": accounts,
            "kategori_sop": categories,
            "months": sorted_months,
            "activity_by_rekening": activity,
        }

    def get_report(
        self,
        *,
        rekening_id: int,
        month: str,
        saldo_awal_override: float | None = None,
    ) -> dict:
        year, month_num, start, end = _parse_month(month)

        with get_connection() as conn:
            rek_row = conn.execute(
                """
                SELECT id, kode_akun, bank_lembaga, no_rekening, atas_nama, peran, is_cash
                FROM rekening_perusahaan
                WHERE id = ? AND is_active = 1
                """,
                (rekening_id,),
            ).fetchone()
            if not rek_row:
                raise RekonError("Rekening tidak ditemukan atau tidak aktif", status_code=404)
            rekening = {**dict(rek_row), "is_cash": bool(rek_row["is_cash"])}

            tx_rows = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT
                        ti.id, ti.tanggal_input, ti.nama_admin, ti.sumber_pencatatan,
                        ti.tab_type, ti.tanggal_transaksi, ti.waktu_transaksi,
                        ti.rekening_sumber_id, ti.rekening_tujuan_id, ti.tipe,
                        ti.kategori_id, ti.penerima_pengirim, ti.keterangan,
                        ti.nominal_pokok, ti.biaya_admin_kode_unik, ti.total_mutasi,
                        ti.status_rekonsiliasi, ti.catatan_rekonsiliasi,
                        ks.nama_kategori,
                        rs.kode_akun AS rekening_sumber,
                        rt.kode_akun AS rekening_tujuan
                    FROM transaksi_internal ti
                    JOIN kategori_sop ks ON ks.id = ti.kategori_id
                    JOIN rekening_perusahaan rs ON rs.id = ti.rekening_sumber_id
                    LEFT JOIN rekening_perusahaan rt ON rt.id = ti.rekening_tujuan_id
                    WHERE (
                        ti.rekening_sumber_id = ?
                        OR (ti.tipe = 'PINDAH_BUKU' AND ti.rekening_tujuan_id = ?)
                    )
                      AND ti.tanggal_transaksi BETWEEN ? AND ?
                    ORDER BY ti.tanggal_transaksi ASC, ti.waktu_transaksi ASC, ti.id ASC
                    """,
                    (rekening_id, rekening_id, start, end),
                ).fetchall()
            ]

            tx_ids = [int(r["id"]) for r in tx_rows]
            files_by_tx: dict[int, list[dict]] = {tid: [] for tid in tx_ids}
            matches_by_tx: dict[int, list[dict]] = {tid: [] for tid in tx_ids}
            if tx_ids:
                placeholders = ",".join("?" for _ in tx_ids)
                for f in conn.execute(
                    f"""
                    SELECT id, transaksi_internal_id, slot, filename, orig_filename, jenis_struk, status_file
                    FROM file_bukti_log
                    WHERE transaksi_internal_id IN ({placeholders})
                    ORDER BY slot ASC, id ASC
                    """,
                    tuple(tx_ids),
                ).fetchall():
                    files_by_tx[int(f["transaksi_internal_id"])].append(
                        {
                            "id": int(f["id"]),
                            "slot": f["slot"],
                            "filename": f["filename"],
                            "orig_filename": f["orig_filename"],
                            "jenis_struk": f["jenis_struk"],
                            "status_file": f["status_file"],
                            "url": f"/api/v1/rekonsiliasi/files/{f['filename']}",
                        }
                    )
                for m in conn.execute(
                    f"""
                    SELECT
                        rm.match_group_id, rm.transaksi_internal_id, rm.mutasi_bank_id,
                        rm.jenis_match, rm.peran_mutasi, rm.selisih_nominal, rm.is_manual, rm.catatan,
                        mb.rekening_id AS mutasi_rekening_id, rp.kode_akun AS mutasi_rekening,
                        mb.tanggal AS mutasi_tanggal, mb.waktu AS mutasi_waktu,
                        mb.uraian AS mutasi_uraian, mb.tipe AS mutasi_tipe, mb.nominal AS mutasi_nominal
                    FROM rekonsiliasi_match rm
                    JOIN mutasi_bank mb ON mb.id = rm.mutasi_bank_id
                    JOIN rekening_perusahaan rp ON rp.id = mb.rekening_id
                    WHERE rm.transaksi_internal_id IN ({placeholders})
                    ORDER BY rm.id ASC
                    """,
                    tuple(tx_ids),
                ).fetchall():
                    matches_by_tx[int(m["transaksi_internal_id"])].append(dict(m))

            batches = [
                dict(b)
                for b in conn.execute(
                    """
                    SELECT id, nama_file, periode_mulai, periode_selesai,
                           saldo_awal_periode, saldo_akhir_periode, jumlah_baris
                    FROM mutasi_upload_batch
                    WHERE rekening_id = ?
                    ORDER BY periode_mulai ASC, id DESC
                    """,
                    (rekening_id,),
                ).fetchall()
            ]
            mutasi_raw = [
                dict(m)
                for m in conn.execute(
                    """
                    SELECT id, batch_id, rekening_id, no_rekening, tanggal, waktu,
                           uraian, tipe, nominal, saldo, status_rekonsiliasi, penyebab_selisih
                    FROM mutasi_bank
                    WHERE rekening_id = ? AND tanggal BETWEEN ? AND ?
                    ORDER BY tanggal ASC, waktu ASC, id ASC
                    """,
                    (rekening_id, start, end),
                ).fetchall()
            ]
            prev_mutasi_rows = [
                dict(m)
                for m in conn.execute(
                    """
                    SELECT id, tanggal, waktu, tipe, nominal, saldo
                    FROM mutasi_bank
                    WHERE rekening_id = ? AND tanggal < ? AND saldo IS NOT NULL
                    ORDER BY tanggal DESC, waktu DESC, id DESC
                    LIMIT 20
                    """,
                    (rekening_id, start),
                ).fetchall()
            ]

            mutasi_ids = [int(m["id"]) for m in mutasi_raw]
            matches_by_mutasi: dict[int, list[dict]] = {mid: [] for mid in mutasi_ids}
            if mutasi_ids:
                placeholders = ",".join("?" for _ in mutasi_ids)
                for m in conn.execute(
                    f"""
                    SELECT
                        rm.match_group_id, rm.transaksi_internal_id, rm.mutasi_bank_id,
                        rm.jenis_match, rm.peran_mutasi, rm.selisih_nominal, rm.is_manual, rm.catatan,
                        ti.tanggal_transaksi, ti.penerima_pengirim, ti.keterangan, ti.total_mutasi,
                        ti.sumber_pencatatan
                    FROM rekonsiliasi_match rm
                    LEFT JOIN transaksi_internal ti ON ti.id = rm.transaksi_internal_id
                    WHERE rm.mutasi_bank_id IN ({placeholders})
                    ORDER BY rm.id ASC
                    """,
                    tuple(mutasi_ids),
                ).fetchall():
                    matches_by_mutasi[int(m["mutasi_bank_id"])].append(dict(m))

        prev_saldo_hint = None
        if prev_mutasi_rows:
            prev_sorted = _sort_mutasi_chronological(list(reversed(prev_mutasi_rows)))
            if prev_sorted and prev_sorted[-1].get("saldo") is not None:
                prev_saldo_hint = float(prev_sorted[-1]["saldo"])

        mutasi_rows = _sort_mutasi_chronological(mutasi_raw, initial_saldo=prev_saldo_hint)
        for m in mutasi_rows:
            m["nominal"] = _round2(m["nominal"])
            m["saldo"] = _round2(m["saldo"]) if m.get("saldo") is not None else None
            m["matches"] = matches_by_mutasi.get(int(m["id"]), [])

        # Auto opening and closing bank balances
        auto_saldo_awal = 0.0
        auto_saldo_sumber = ""
        saldo_akhir_bank: float | None = None
        mutasi_periode_mulai: str | None = None
        mutasi_periode_selesai: str | None = None
        warnings: list[str] = []

        if rekening["is_cash"]:
            auto_saldo_sumber = "Kas tunai tidak memiliki mutasi bank — isi saldo awal secara manual bila diperlukan."
        else:
            overlapping_batches = [
                b for b in batches if b["periode_mulai"] <= end and b["periode_selesai"] >= start
            ]
            covering_start = [
                b for b in overlapping_batches if b["periode_mulai"] <= start <= b["periode_selesai"]
            ]

            if covering_start:
                exact_start = [
                    b
                    for b in covering_start
                    if b["periode_mulai"] == start and b["saldo_awal_periode"] is not None
                ]
                if exact_start:
                    chosen = exact_start[0]
                    auto_saldo_awal = _round2(chosen["saldo_awal_periode"])
                    auto_saldo_sumber = f'Saldo awal mutasi "{chosen["nama_file"]}"'
                elif mutasi_rows and mutasi_rows[0].get("saldo") is not None:
                    oldest = mutasi_rows[0]
                    auto_saldo_awal = _round2(
                        oldest["saldo"] - oldest["nominal"]
                        if oldest["tipe"] == "CR"
                        else oldest["saldo"] + oldest["nominal"]
                    )
                    auto_saldo_sumber = f'Diturunkan dari mutasi pertama {_format_tanggal_id(oldest["tanggal"])}'
                elif prev_saldo_hint is not None:
                    auto_saldo_awal = _round2(prev_saldo_hint)
                    auto_saldo_sumber = "Saldo akhir mutasi periode sebelumnya"
                else:
                    auto_saldo_sumber = "Saldo awal tidak tersedia dari mutasi — isi secara manual."
            elif mutasi_rows or overlapping_batches:
                first_batch = next(
                    (b for b in overlapping_batches if b["saldo_awal_periode"] is not None),
                    None,
                )
                first_mutasi_date = (
                    mutasi_rows[0]["tanggal"]
                    if mutasi_rows
                    else (first_batch["periode_mulai"] if first_batch else start)
                )
                if prev_saldo_hint is not None:
                    auto_saldo_awal = _round2(prev_saldo_hint)
                    auto_saldo_sumber = "Saldo akhir mutasi sebelum bulan ini"
                elif first_batch is not None:
                    auto_saldo_awal = _round2(first_batch["saldo_awal_periode"])
                    auto_saldo_sumber = (
                        f'Saldo awal mutasi "{first_batch["nama_file"]}" '
                        f'(mulai {_format_tanggal_id(first_batch["periode_mulai"])})'
                    )
                elif mutasi_rows and mutasi_rows[0].get("saldo") is not None:
                    oldest = mutasi_rows[0]
                    auto_saldo_awal = _round2(
                        oldest["saldo"] - oldest["nominal"]
                        if oldest["tipe"] == "CR"
                        else oldest["saldo"] + oldest["nominal"]
                    )
                    auto_saldo_sumber = f'Diturunkan dari mutasi pertama {_format_tanggal_id(oldest["tanggal"])}'
                else:
                    auto_saldo_sumber = "Saldo awal tidak bisa dihitung dari mutasi — isi secara manual."

                if first_mutasi_date > start and prev_saldo_hint is None:
                    has_earlier_tx = any(t["tanggal_transaksi"] < first_mutasi_date for t in tx_rows)
                    if has_earlier_tx:
                        warnings.append(
                            f"Mutasi bank bulan ini baru dimulai {_format_tanggal_id(first_mutasi_date)}, "
                            f"sedangkan ada transaksi catatan sebelum tanggal tersebut. Periksa Saldo Awal."
                        )
            elif prev_saldo_hint is not None:
                auto_saldo_awal = _round2(prev_saldo_hint)
                last_prev_date = prev_mutasi_rows[0]["tanggal"]
                auto_saldo_sumber = (
                    f"Saldo akhir mutasi sebelumnya ({_format_tanggal_id(last_prev_date)})"
                )
            else:
                auto_saldo_sumber = "Belum ada mutasi bank bulan ini — isi saldo awal secara manual."

            if mutasi_rows:
                mutasi_periode_mulai = mutasi_rows[0]["tanggal"]
                mutasi_periode_selesai = mutasi_rows[-1]["tanggal"]
                last_with_saldo = next((r for r in reversed(mutasi_rows) if r.get("saldo") is not None), None)
                if last_with_saldo is not None:
                    saldo_akhir_bank = _round2(last_with_saldo["saldo"])
            if saldo_akhir_bank is None and overlapping_batches:
                ending_batches = [
                    b
                    for b in overlapping_batches
                    if b["periode_selesai"] <= end and b["saldo_akhir_periode"] is not None
                ]
                if ending_batches:
                    last_batch = max(ending_batches, key=lambda b: (b["periode_selesai"], b["id"]))
                    saldo_akhir_bank = _round2(last_batch["saldo_akhir_periode"])
                    mutasi_periode_mulai = mutasi_periode_mulai or last_batch["periode_mulai"]
                    mutasi_periode_selesai = mutasi_periode_selesai or last_batch["periode_selesai"]

            if mutasi_periode_selesai and mutasi_periode_selesai < end:
                has_later_tx = any(t["tanggal_transaksi"] > mutasi_periode_selesai for t in tx_rows)
                if has_later_tx:
                    warnings.append(
                        f"Mutasi bank hanya mencakup sampai {_format_tanggal_id(mutasi_periode_selesai)}, "
                        f"sedangkan ada transaksi catatan setelah tanggal tersebut."
                    )

        effective_saldo_awal = _round2(
            saldo_awal_override if saldo_awal_override is not None else auto_saldo_awal
        )

        report_rows: list[dict] = []
        running_saldo = effective_saldo_awal
        total_debet_transaksi = 0.0
        total_kredit = 0.0

        for tx in tx_rows:
            tid = int(tx["id"])
            mapped = _map_tx_to_cash_report_row(
                tx,
                rekening_id,
                files_by_tx.get(tid, []),
                matches_by_tx.get(tid, []),
            )
            if mapped is None:
                continue
            running_saldo = _round2(running_saldo + mapped["debet"] - mapped["kredit"])
            mapped["saldo"] = running_saldo
            total_debet_transaksi = _round2(total_debet_transaksi + mapped["debet"])
            total_kredit = _round2(total_kredit + mapped["kredit"])
            report_rows.append(mapped)

        sub_total_debet = _round2(effective_saldo_awal + total_debet_transaksi)
        sisa_saldo = _round2(sub_total_debet - total_kredit)
        saldo_akhir = running_saldo

        selisih_saldo: float | None = None
        is_balanced: bool | None = None
        if saldo_akhir_bank is not None:
            selisih_saldo = _round2(saldo_akhir - saldo_akhir_bank)
            is_balanced = abs(selisih_saldo) <= 0.01
            if is_balanced:
                selisih_saldo = 0.0

        tx_matched_statuses = {"SESUAI", "SELISIH_KODE_UNIK_ADMIN", "PINDAH_BUKU_COCOK"}
        tx_matched = sum(1 for r in report_rows if r["status_rekonsiliasi"] in tx_matched_statuses)
        tx_unmatched = len(report_rows) - tx_matched

        mutasi_belum_tercatat = sum(1 for m in mutasi_rows if m["status_rekonsiliasi"] == "BELUM_TERCATAT")
        mutasi_belum_rekon = sum(1 for m in mutasi_rows if m["status_rekonsiliasi"] == "BELUM_REKON")
        mutasi_matched = len(mutasi_rows) - mutasi_belum_tercatat - mutasi_belum_rekon

        title = (
            "Cash Report Operasional"
            if rekening["is_cash"]
            else f"Cash Report {rekening['kode_akun']}"
        )
        subtitle = (
            ""
            if rekening["is_cash"]
            else " - ".join(p for p in [rekening["bank_lembaga"], rekening["no_rekening"]] if p and p != "-")
        )
        sheet_name = f"{title}-{BULAN_ID[month_num - 1]}"
        file_name = (
            f"Cash_Report_{_sanitize_filename_part(rekening['kode_akun'])}"
            f"-{BULAN_ID[month_num - 1]}_{year}-PT_Lokal_Komoditi_Indonesia.xlsx"
        )

        return {
            "company": COMPANY_NAME,
            "title": title,
            "subtitle": subtitle,
            "periode": f"Periode {_month_label(year, month_num)}",
            "month": month,
            "month_label": _month_label(year, month_num),
            "start_date": start,
            "end_date": end,
            "sheet_name": sheet_name,
            "file_name": file_name,
            "rekening": rekening,
            "auto_saldo_awal": auto_saldo_awal,
            "auto_saldo_sumber": auto_saldo_sumber,
            "saldo_awal": effective_saldo_awal,
            "is_saldo_manual": saldo_awal_override is not None,
            "total_debet_transaksi": total_debet_transaksi,
            "total_kredit": total_kredit,
            "sub_total_debet": sub_total_debet,
            "sisa_saldo": sisa_saldo,
            "saldo_akhir": saldo_akhir,
            "saldo_akhir_bank": saldo_akhir_bank,
            "selisih_saldo": selisih_saldo,
            "is_balanced": is_balanced,
            "mutasi_periode_mulai": mutasi_periode_mulai,
            "mutasi_periode_selesai": mutasi_periode_selesai,
            "warnings": warnings,
            "summary": {
                "tx_total": len(report_rows),
                "tx_matched": tx_matched,
                "tx_unmatched": tx_unmatched,
                "mutasi_total": len(mutasi_rows),
                "mutasi_matched": mutasi_matched,
                "mutasi_belum_rekon": mutasi_belum_rekon,
                "mutasi_belum_tercatat": mutasi_belum_tercatat,
            },
            "rows": report_rows,
            "mutasi_rows": mutasi_rows,
        }

    def manual_match(
        self,
        *,
        user: UserPublic,
        transaksi_id: int,
        mutasi_ids: list[int],
        catatan: str = "",
    ) -> dict:
        unique_mutasi_ids = list(dict.fromkeys(int(mid) for mid in mutasi_ids))
        if not unique_mutasi_ids:
            raise RekonError("Pilih minimal satu baris mutasi bank")
        user_id = self._user_id(user.username)
        note = catatan.strip() or "Manual match melalui menu Rekonsiliasi"

        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            tx = conn.execute(
                """
                SELECT ti.id, ti.tipe, ti.rekening_sumber_id, ti.rekening_tujuan_id,
                       ti.nominal_pokok, ti.total_mutasi, rs.is_cash AS sumber_is_cash
                FROM transaksi_internal ti
                JOIN rekening_perusahaan rs ON rs.id = ti.rekening_sumber_id
                WHERE ti.id = ?
                """,
                (transaksi_id,),
            ).fetchone()
            if not tx:
                conn.rollback()
                raise RekonError("Transaksi internal tidak ditemukan", status_code=404)

            existing_tx_match = conn.execute(
                "SELECT 1 FROM rekonsiliasi_match WHERE transaksi_internal_id = ? LIMIT 1",
                (transaksi_id,),
            ).fetchone()
            if existing_tx_match:
                conn.rollback()
                raise RekonError("Transaksi ini sudah memiliki pasangan rekonsiliasi; lepas kecocokan dulu", status_code=409)

            placeholders = ",".join("?" for _ in unique_mutasi_ids)
            mutasi_rows = conn.execute(
                f"SELECT id, rekening_id, tipe, nominal FROM mutasi_bank WHERE id IN ({placeholders})",
                tuple(unique_mutasi_ids),
            ).fetchall()
            if len(mutasi_rows) != len(unique_mutasi_ids):
                conn.rollback()
                raise RekonError("Sebagian baris mutasi bank tidak ditemukan", status_code=404)

            existing_mut_match = conn.execute(
                f"SELECT mutasi_bank_id FROM rekonsiliasi_match WHERE mutasi_bank_id IN ({placeholders}) LIMIT 1",
                tuple(unique_mutasi_ids),
            ).fetchone()
            if existing_mut_match:
                conn.rollback()
                raise RekonError(
                    f"Mutasi #{existing_mut_match['mutasi_bank_id']} sudah terhubung dengan transaksi lain",
                    status_code=409,
                )

            tx_tipe = tx["tipe"]
            sumber_id = int(tx["rekening_sumber_id"])
            tujuan_id = int(tx["rekening_tujuan_id"]) if tx["rekening_tujuan_id"] is not None else None

            if tx_tipe in {"MASUK", "KELUAR"}:
                if tx["sumber_is_cash"]:
                    conn.rollback()
                    raise RekonError("Transaksi kas tunai tidak dapat dicocokkan dengan mutasi bank")
                expected_mut_tipe = "CR" if tx_tipe == "MASUK" else "DB"
                for m in mutasi_rows:
                    if int(m["rekening_id"]) != sumber_id:
                        conn.rollback()
                        raise RekonError("Rekening mutasi tidak sesuai dengan rekening sumber transaksi")
                    if m["tipe"] != expected_mut_tipe:
                        conn.rollback()
                        raise RekonError(
                            f"Arah mutasi ({m['tipe']}) tidak cocok dengan tipe transaksi ({tx_tipe})"
                        )
                total_mutasi_sum = _round2(sum(float(m["nominal"]) for m in mutasi_rows))
                diff = _round2(total_mutasi_sum - float(tx["total_mutasi"]))
                is_exact = abs(diff) < 1
                jenis_match = "SPLIT_ADMIN" if len(mutasi_rows) >= 2 else "MANUAL"
                status_final = "SESUAI" if is_exact else "SELISIH_KODE_UNIK_ADMIN"

                sorted_mut = sorted(mutasi_rows, key=lambda r: float(r["nominal"]), reverse=True)
                group_id = f"grp_{uuid.uuid4().hex[:12]}"
                for idx, m in enumerate(sorted_mut):
                    if len(sorted_mut) == 1:
                        peran = "UTAMA"
                        row_diff = diff
                    elif idx == 0:
                        peran = "POKOK"
                        row_diff = _round2(float(m["nominal"]) - float(tx["nominal_pokok"]))
                    else:
                        peran = "BIAYA_ADMIN"
                        row_diff = _round2(float(m["nominal"]))
                    conn.execute(
                        """
                        INSERT INTO rekonsiliasi_match (
                            match_group_id, transaksi_internal_id, mutasi_bank_id,
                            jenis_match, peran_mutasi, selisih_nominal, is_manual,
                            matched_by_user_id, catatan
                        ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                        """,
                        (group_id, transaksi_id, m["id"], jenis_match, peran, row_diff, user_id, note),
                    )
                conn.execute(
                    "UPDATE transaksi_internal SET status_rekonsiliasi = ?, catatan_rekonsiliasi = ? WHERE id = ?",
                    (status_final, note, transaksi_id),
                )
                conn.execute(
                    f"UPDATE mutasi_bank SET status_rekonsiliasi = ? WHERE id IN ({placeholders})",
                    (status_final, *unique_mutasi_ids),
                )
                conn.commit()
                return {
                    "match_group_id": group_id,
                    "transaksi_id": transaksi_id,
                    "mutasi_ids": unique_mutasi_ids,
                    "jenis_match": jenis_match,
                    "status_rekonsiliasi": status_final,
                    "selisih_nominal": diff,
                }

            # PINDAH_BUKU
            has_out = False
            has_in = False
            links: list[tuple[int, str, float]] = []
            in_target = float(tx["nominal_pokok"]) if float(tx["nominal_pokok"]) > 0 else float(tx["total_mutasi"])
            for m in mutasi_rows:
                rid = int(m["rekening_id"])
                if rid == sumber_id and m["tipe"] == "DB":
                    has_out = True
                    links.append((int(m["id"]), "PINDAH_KELUAR", _round2(float(m["nominal"]) - float(tx["total_mutasi"]))))
                elif tujuan_id is not None and rid == tujuan_id and m["tipe"] == "CR":
                    has_in = True
                    links.append((int(m["id"]), "PINDAH_MASUK", _round2(float(m["nominal"]) - in_target)))
                else:
                    conn.rollback()
                    raise RekonError("Baris mutasi tidak sesuai rekening/arah transaksi Pindah Buku")

            jenis_match = "PINDAH_BUKU_PAIR" if (has_out and has_in) else "MANUAL"
            group_id = f"grp_{uuid.uuid4().hex[:12]}"
            for mid, peran, row_diff in links:
                conn.execute(
                    """
                    INSERT INTO rekonsiliasi_match (
                        match_group_id, transaksi_internal_id, mutasi_bank_id,
                        jenis_match, peran_mutasi, selisih_nominal, is_manual,
                        matched_by_user_id, catatan
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (group_id, transaksi_id, mid, jenis_match, peran, row_diff, user_id, note),
                )
            conn.execute(
                "UPDATE transaksi_internal SET status_rekonsiliasi = 'PINDAH_BUKU_COCOK', catatan_rekonsiliasi = ? WHERE id = ?",
                (note, transaksi_id),
            )
            conn.execute(
                f"UPDATE mutasi_bank SET status_rekonsiliasi = 'PINDAH_BUKU' WHERE id IN ({placeholders})",
                tuple(unique_mutasi_ids),
            )
            conn.commit()
            return {
                "match_group_id": group_id,
                "transaksi_id": transaksi_id,
                "mutasi_ids": unique_mutasi_ids,
                "jenis_match": jenis_match,
                "status_rekonsiliasi": "PINDAH_BUKU_COCOK",
                "selisih_nominal": 0.0,
            }

    def unmatch(self, *, match_group_id: str) -> dict:
        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """
                SELECT transaksi_internal_id, mutasi_bank_id
                FROM rekonsiliasi_match
                WHERE match_group_id = ?
                """,
                (match_group_id,),
            ).fetchall()
            if not rows:
                conn.rollback()
                raise RekonError("Data kecocokan rekonsiliasi tidak ditemukan", status_code=404)

            tx_ids = sorted({int(r["transaksi_internal_id"]) for r in rows if r["transaksi_internal_id"] is not None})
            mut_ids = sorted({int(r["mutasi_bank_id"]) for r in rows})
            conn.execute("DELETE FROM rekonsiliasi_match WHERE match_group_id = ?", (match_group_id,))

            for tid in tx_ids:
                remaining = conn.execute(
                    "SELECT 1 FROM rekonsiliasi_match WHERE transaksi_internal_id = ? LIMIT 1",
                    (tid,),
                ).fetchone()
                if not remaining:
                    conn.execute(
                        "UPDATE transaksi_internal SET status_rekonsiliasi = 'BELUM_REKON', catatan_rekonsiliasi = '' WHERE id = ?",
                        (tid,),
                    )

            for mid in mut_ids:
                remaining = conn.execute(
                    "SELECT 1 FROM rekonsiliasi_match WHERE mutasi_bank_id = ? LIMIT 1",
                    (mid,),
                ).fetchone()
                if not remaining:
                    conn.execute(
                        "UPDATE mutasi_bank SET status_rekonsiliasi = 'BELUM_REKON' WHERE id = ?",
                        (mid,),
                    )
            conn.commit()
        return {"match_group_id": match_group_id, "unmatched_tx_ids": tx_ids, "unmatched_mutasi_ids": mut_ids}

    def create_penyesuaian(self, *, user: UserPublic, payload: RekonPenyesuaianRequest) -> dict:
        user_id = self._user_id(user.username)
        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            mut = conn.execute(
                "SELECT id, rekening_id, tanggal, waktu, uraian, tipe, nominal FROM mutasi_bank WHERE id = ?",
                (payload.mutasi_id,),
            ).fetchone()
            if not mut:
                conn.rollback()
                raise RekonError("Baris mutasi bank tidak ditemukan", status_code=404)

            already = conn.execute(
                "SELECT 1 FROM rekonsiliasi_match WHERE mutasi_bank_id = ? LIMIT 1",
                (payload.mutasi_id,),
            ).fetchone()
            if already:
                conn.rollback()
                raise RekonError("Mutasi ini sudah cocok dengan transaksi; lepas kecocokan terlebih dahulu", status_code=409)

            cat = conn.execute(
                "SELECT id FROM kategori_sop WHERE id = ? AND is_active = 1",
                (payload.kategori_id,),
            ).fetchone()
            if not cat:
                conn.rollback()
                raise RekonError("Kategori SOP tidak valid")

            mut_rek_id = int(mut["rekening_id"])
            mut_tipe = mut["tipe"]

            if payload.tipe == "MASUK":
                if mut_tipe != "CR":
                    conn.rollback()
                    raise RekonError("Mutasi DB (uang keluar) tidak dapat dicatat sebagai MASUK")
                sumber_id = mut_rek_id
                tujuan_id = None
                peran = "UTAMA"
                tx_status = "SESUAI"
                mut_status = "SESUAI"
            elif payload.tipe == "KELUAR":
                if mut_tipe != "DB":
                    conn.rollback()
                    raise RekonError("Mutasi CR (uang masuk) tidak dapat dicatat sebagai KELUAR")
                sumber_id = mut_rek_id
                tujuan_id = None
                peran = "UTAMA"
                tx_status = "SESUAI"
                mut_status = "SESUAI"
            else:
                if mut_tipe == "DB":
                    sumber_id = mut_rek_id
                    tujuan_id = payload.rekening_tujuan_id
                    peran = "PINDAH_KELUAR"
                else:
                    sumber_id = payload.rekening_sumber_id
                    tujuan_id = mut_rek_id
                    peran = "PINDAH_MASUK"
                if sumber_id is None or tujuan_id is None:
                    conn.rollback()
                    raise RekonError("Rekening sumber dan tujuan wajib diisi untuk Pindah Buku")
                if sumber_id == tujuan_id:
                    conn.rollback()
                    raise RekonError("Rekening sumber dan tujuan tidak boleh sama")
                other_id = tujuan_id if mut_tipe == "DB" else sumber_id
                other_acc = conn.execute(
                    "SELECT id FROM rekening_perusahaan WHERE id = ? AND is_active = 1",
                    (other_id,),
                ).fetchone()
                if not other_acc:
                    conn.rollback()
                    raise RekonError("Rekening lawan Pindah Buku tidak valid")
                tx_status = "PINDAH_BUKU_COCOK"
                mut_status = "PINDAH_BUKU"

            keterangan = payload.keterangan.strip() or mut["uraian"]
            penerima = payload.penerima_pengirim.strip()
            note = payload.catatan.strip() or "Penyesuaian mutasi bank"
            nominal = float(mut["nominal"])

            tx_id = conn.execute(
                """
                INSERT INTO transaksi_internal (
                    staging_id, created_by_user_id, nama_admin, tanggal_input,
                    sumber_pencatatan, tab_type, tanggal_transaksi, waktu_transaksi,
                    rekening_sumber_id, rekening_tujuan_id, tipe, kategori_id,
                    penerima_pengirim, keterangan, nominal_pokok,
                    biaya_admin_kode_unik, total_mutasi, status_rekonsiliasi, catatan_rekonsiliasi
                ) VALUES (NULL, ?, ?, ?, 'PENYESUAIAN_MUTASI', 'manual', ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    user_id,
                    user.full_name,
                    date.today().isoformat(),
                    mut["tanggal"],
                    mut["waktu"] or "00:00:00",
                    sumber_id,
                    tujuan_id,
                    payload.tipe,
                    payload.kategori_id,
                    penerima,
                    keterangan,
                    nominal,
                    nominal,
                    tx_status,
                    note,
                ),
            ).lastrowid

            group_id = f"grp_{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO rekonsiliasi_match (
                    match_group_id, transaksi_internal_id, mutasi_bank_id,
                    jenis_match, peran_mutasi, selisih_nominal, is_manual,
                    matched_by_user_id, catatan
                ) VALUES (?, ?, ?, 'MANUAL', ?, 0, 1, ?, ?)
                """,
                (group_id, tx_id, payload.mutasi_id, peran, user_id, note),
            )
            conn.execute(
                "UPDATE mutasi_bank SET status_rekonsiliasi = ? WHERE id = ?",
                (mut_status, payload.mutasi_id),
            )
            conn.commit()
        return {
            "transaksi_id": tx_id,
            "match_group_id": group_id,
            "mutasi_id": payload.mutasi_id,
            "status_rekonsiliasi": tx_status,
        }

    def delete_penyesuaian(self, *, transaksi_id: int) -> dict:
        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            tx = conn.execute(
                "SELECT id, sumber_pencatatan FROM transaksi_internal WHERE id = ?",
                (transaksi_id,),
            ).fetchone()
            if not tx:
                conn.rollback()
                raise RekonError("Transaksi penyesuaian tidak ditemukan", status_code=404)
            if tx["sumber_pencatatan"] != "PENYESUAIAN_MUTASI":
                conn.rollback()
                raise RekonError("Hanya transaksi penyesuaian mutasi yang dapat dihapus dari menu Rekonsiliasi")
            unlink_reconciliation_for_transaction(conn, transaksi_id)
            conn.execute("DELETE FROM transaksi_internal WHERE id = ?", (transaksi_id,))
            conn.commit()
        return {"transaksi_id": transaksi_id, "message": "Penyesuaian mutasi berhasil dihapus"}

    def auto_run(self, *, rekening_id: int | None = None) -> dict:
        with get_connection() as conn:
            if rekening_id is not None:
                tx_rows = conn.execute(
                    """
                    SELECT id FROM transaksi_internal
                    WHERE status_rekonsiliasi IN ('BELUM_REKON', 'MUTASI_BELUM_ADA')
                      AND (rekening_sumber_id = ? OR rekening_tujuan_id = ?)
                    ORDER BY tanggal_transaksi ASC, id ASC
                    """,
                    (rekening_id, rekening_id),
                ).fetchall()
            else:
                tx_rows = conn.execute(
                    """
                    SELECT id FROM transaksi_internal
                    WHERE status_rekonsiliasi IN ('BELUM_REKON', 'MUTASI_BELUM_ADA')
                    ORDER BY tanggal_transaksi ASC, id ASC
                    """
                ).fetchall()

        matched = 0
        for row in tx_rows:
            if auto_reconcile_transaction(int(row["id"])).get("matched"):
                matched += 1

        with get_connection() as conn:
            where_rek = "AND rekening_id = ?" if rekening_id is not None else ""
            params = (rekening_id,) if rekening_id is not None else ()
            unmatched_mut = conn.execute(
                f"""
                SELECT id, uraian FROM mutasi_bank
                WHERE status_rekonsiliasi = 'BELUM_REKON' {where_rek}
                """,
                params,
            ).fetchall()
            for mut in unmatched_mut:
                reason = _classify_unmatched_mutasi_reason(mut["uraian"])
                conn.execute(
                    """
                    UPDATE mutasi_bank
                    SET status_rekonsiliasi = 'BELUM_TERCATAT',
                        penyebab_selisih = CASE WHEN penyebab_selisih = '' THEN ? ELSE penyebab_selisih END
                    WHERE id = ?
                    """,
                    (reason, mut["id"]),
                )
            conn.commit()
        return {"matched_transactions": matched, "unmatched_mutasi": len(unmatched_mut)}

    def _user_id(self, username: str) -> int:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE username = ?",
                (username.strip().lower(),),
            ).fetchone()
        if not row:
            raise RekonError("User tidak ditemukan", status_code=401)
        return int(row["id"])


rekonsiliasi_service = RekonsiliasiService()
