from __future__ import annotations

from datetime import date, timedelta
import sqlite3
import uuid

from app.core.database import get_connection

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
