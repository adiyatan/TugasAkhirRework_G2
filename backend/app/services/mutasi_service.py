from __future__ import annotations

from datetime import date
import hashlib
import re

from app.core.config import settings
from app.core.database import get_connection
from app.schemas.auth import UserPublic
from app.schemas.mutasi import (
    MutasiBalanceSummary,
    MutasiMetadata,
    MutasiRowInput,
    MutasiSaveRequest,
)
from app.services.mutasi_parser import MutasiParseError, parse_mutasi_pdf
from app.services.rekonsiliasi_service import (
    auto_reconcile_mutasi_batch,
    recalculate_reconciliation_for_transactions,
)


class MutasiError(Exception):
    status_code = 400

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class MutasiConflictError(MutasiError):
    status_code = 409


class MutasiUpstreamError(MutasiError):
    status_code = 502


def _digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _account_numbers(raw: str) -> list[str]:
    return [d for part in re.split(r"[,;/]+", raw) if (d := _digits(part))]


def _normalize_uraian(value: str) -> str:
    return " ".join(value.split()).strip().upper()


def _format_num(value: float | None) -> str:
    if value is None:
        return "NONE"
    rounded = round(float(value), 2)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.2f}"


def compute_dedup_signature(
    *,
    rekening_id: int,
    tanggal: str,
    waktu: str,
    tipe: str,
    nominal: float,
    uraian: str,
    saldo: float | None,
    occurrence: int = 0,
) -> str:
    """Compute unique dedup_signature for a mutasi_bank row."""
    tail = f"SALDO={_format_num(saldo)}" if saldo is not None else f"OCC={occurrence}"
    raw = "|".join(
        [
            str(rekening_id),
            tanggal.strip(),
            waktu.strip(),
            tipe.strip().upper(),
            _format_num(nominal),
            _normalize_uraian(uraian),
            tail,
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_balance_summary(
    rows: list[MutasiRowInput],
    *,
    printed_saldo_awal: float | None = None,
    printed_saldo_akhir: float | None = None,
) -> MutasiBalanceSummary:
    dates = [row.tanggal for row in rows]
    periode_mulai = min(dates)
    periode_selesai = max(dates)
    total_cr = round(sum(row.nominal for row in rows if row.tipe == "CR"), 2)
    total_db = round(sum(row.nominal for row in rows if row.tipe == "DB"), 2)

    first = rows[0]
    last = rows[-1]
    saldo_awal: float | None = None
    if first.saldo is not None:
        saldo_awal = round(
            first.saldo - first.nominal if first.tipe == "CR" else first.saldo + first.nominal,
            2,
        )
    saldo_akhir: float | None = round(last.saldo, 2) if last.saldo is not None else None

    expected: float | None = None
    selisih: float | None = None
    balance_valid = True

    if saldo_awal is not None and saldo_akhir is not None:
        expected = round(saldo_awal + total_cr - total_db, 2)
        selisih = round(saldo_akhir - expected, 2)
        balance_valid = abs(selisih) <= 0.01

        running = saldo_awal
        for row in rows:
            running = running + row.nominal if row.tipe == "CR" else running - row.nominal
            if row.saldo is not None and abs(running - row.saldo) > 0.01:
                balance_valid = False
                break

    if printed_saldo_awal is not None and saldo_awal is not None and abs(printed_saldo_awal - saldo_awal) > 0.01:
        balance_valid = False
    if printed_saldo_akhir is not None and saldo_akhir is not None and abs(printed_saldo_akhir - saldo_akhir) > 0.01:
        balance_valid = False

    return MutasiBalanceSummary(
        periode_mulai=periode_mulai,
        periode_selesai=periode_selesai,
        saldo_awal_periode=saldo_awal,
        total_cr=total_cr,
        total_db=total_db,
        saldo_akhir_periode=saldo_akhir,
        printed_saldo_awal=round(printed_saldo_awal, 2) if printed_saldo_awal is not None else None,
        printed_saldo_akhir=round(printed_saldo_akhir, 2) if printed_saldo_akhir is not None else None,
        expected_saldo_akhir=expected,
        selisih_saldo=selisih,
        balance_valid=balance_valid,
    )


class MutasiService:
    """Business logic for Input Mutasi Bank."""

    def get_metadata(self) -> MutasiMetadata:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, kode_akun, bank_lembaga, no_rekening, atas_nama, peran
                FROM rekening_perusahaan
                WHERE is_active = 1 AND is_cash = 0
                ORDER BY id ASC
                """
            ).fetchall()
        return MutasiMetadata(rekening_perusahaan=[dict(row) for row in rows])

    async def preview(
        self,
        *,
        filename: str,
        data: bytes,
        rekening_id: int | None = None,
    ) -> dict:
        if not filename.lower().endswith(".pdf"):
            raise MutasiError("File mutasi wajib berformat PDF (.pdf)")
        if not data:
            raise MutasiError("File PDF kosong")
        max_bytes = max(1, settings.max_upload_mb) * 1024 * 1024
        if len(data) > max_bytes:
            raise MutasiError(f"Ukuran file PDF melebihi batas {settings.max_upload_mb} MB")

        accounts = [row.model_dump() for row in self.get_metadata().rekening_perusahaan]
        selected_account: dict | None = None
        if rekening_id is not None:
            selected_account = self._get_non_cash_account(rekening_id)

        file_hash = hashlib.sha256(data).hexdigest()
        warnings: list[str] = []
        duplicate_batch = self._find_batch_by_hash(file_hash)
        if duplicate_batch:
            warnings.append(
                f"File PDF ini sudah pernah diunggah pada Batch #{duplicate_batch['id']} ({duplicate_batch['nama_file']})."
            )

        bank_hint = selected_account["kode_akun"] if selected_account else "AUTO"
        try:
            parsed = await parse_mutasi_pdf(data, bank_hint=bank_hint, accounts=accounts)
        except MutasiParseError as exc:
            message = str(exc)
            if "Vision AI gagal" in message or "JSON" in message:
                raise MutasiUpstreamError(message) from exc
            raise MutasiError(message) from exc

        matched_account = self._match_account_by_number(parsed.no_rekening, accounts)
        if selected_account is None:
            if matched_account is None:
                raise MutasiError(
                    "Nomor rekening pada PDF tidak ditemukan di rekening_perusahaan; pilih target rekening secara manual"
                )
            target_account = matched_account
        else:
            target_account = selected_account
            if matched_account and matched_account["id"] != target_account["id"]:
                warnings.append(
                    f"Nomor rekening di PDF ({parsed.no_rekening}) terdeteksi milik {matched_account['kode_akun']}, bukan {target_account['kode_akun']}."
                )

        row_inputs = [
            MutasiRowInput(
                tanggal=row.tanggal,
                waktu=row.waktu,
                uraian=row.uraian,
                tipe=row.tipe,
                nominal=row.nominal,
                saldo=row.saldo,
            )
            for row in parsed.rows
        ]
        summary = compute_balance_summary(
            row_inputs,
            printed_saldo_awal=parsed.printed_saldo_awal,
            printed_saldo_akhir=parsed.printed_saldo_akhir,
        )
        if not summary.balance_valid:
            if (
                summary.printed_saldo_awal is not None
                and summary.saldo_awal_periode is not None
                and abs(summary.printed_saldo_awal - summary.saldo_awal_periode) > 0.01
            ):
                warnings.append(
                    "PERINGATAN KERAS: Saldo awal turunan baris pertama tidak cocok dengan Saldo Awal tercetak di PDF. Kemungkinan baris awal terlewat."
                )
            elif (
                summary.printed_saldo_akhir is not None
                and summary.saldo_akhir_periode is not None
                and abs(summary.printed_saldo_akhir - summary.saldo_akhir_periode) > 0.01
            ):
                warnings.append(
                    "PERINGATAN KERAS: Saldo akhir baris terakhir tidak cocok dengan Saldo Akhir tercetak di PDF. Kemungkinan baris akhir terlewat."
                )
            else:
                diff_fmt = (
                    f"Rp{abs(summary.selisih_saldo):,.0f}".replace(",", ".")
                    if summary.selisih_saldo is not None
                    else "tidak konsisten"
                )
                warnings.append(
                    f"PERINGATAN KERAS: Saldo awal + CR - DB tidak sama dengan saldo akhir ({diff_fmt}). Periksa baris yang mungkin terlewat."
                )

        signatures = self._compute_batch_signatures(target_account["id"], row_inputs)
        existing_sigs = self._existing_signatures(target_account["id"])
        already_in_db_count = sum(1 for sig in signatures if sig in existing_sigs)
        if already_in_db_count:
            warnings.append(
                f"{already_in_db_count} dari {len(row_inputs)} baris sudah ada di database dan akan dilewati saat simpan."
            )

        return {
            "nama_file": filename,
            "file_hash": file_hash,
            "rekening": target_account,
            "detected_no_rekening": parsed.no_rekening,
            "metode_ekstraksi": parsed.metode_ekstraksi,
            "duplicate_batch": duplicate_batch,
            "summary": summary.model_dump(),
            "already_in_db_count": already_in_db_count,
            "warnings": warnings,
            "rows": [
                {
                    **row.model_dump(),
                    "already_exists": sig in existing_sigs,
                }
                for row, sig in zip(row_inputs, signatures, strict=True)
            ],
        }

    def save(self, *, user: UserPublic, payload: MutasiSaveRequest) -> dict:
        if not re.fullmatch(r"[0-9a-fA-F]{64}", payload.file_hash):
            raise MutasiError("file_hash harus SHA-256 64 karakter hex")
        account = self._get_non_cash_account(payload.rekening_id)
        for idx, row in enumerate(payload.rows, start=1):
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row.tanggal):
                raise MutasiError(f"Tanggal baris #{idx} tidak valid")
            try:
                date.fromisoformat(row.tanggal)
            except ValueError as exc:
                raise MutasiError(f"Tanggal kalender baris #{idx} tidak valid") from exc
            if not re.fullmatch(r"\d{2}:\d{2}:\d{2}", row.waktu):
                raise MutasiError(f"Waktu baris #{idx} tidak valid")

        user_id = self._user_id(user.username)
        summary = compute_balance_summary(payload.rows)
        signatures = self._compute_batch_signatures(account["id"], payload.rows)
        account_nums = _account_numbers(account["no_rekening"])
        requested_no = _digits(payload.no_rekening)
        if requested_no and any(
            requested_no == num or (len(requested_no) >= 6 and (requested_no in num or num in requested_no))
            for num in account_nums
        ):
            no_rek_primary = requested_no
        else:
            no_rek_primary = account_nums[0] if account_nums else account["no_rekening"]

        affected_tx_ids: list[int] = []
        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing_batch = conn.execute(
                    "SELECT id, nama_file FROM mutasi_upload_batch WHERE file_hash = ?",
                    (payload.file_hash.lower(),),
                ).fetchone()
                if existing_batch:
                    if not payload.replace_existing:
                        raise MutasiConflictError(
                            f"File PDF sudah tercatat pada Batch #{existing_batch['id']} ({existing_batch['nama_file']})"
                        )
                    linked_rows = conn.execute(
                        """
                        SELECT DISTINCT rm.transaksi_internal_id
                        FROM rekonsiliasi_match rm
                        JOIN mutasi_bank mb ON mb.id = rm.mutasi_bank_id
                        WHERE mb.batch_id = ? AND rm.transaksi_internal_id IS NOT NULL
                        """,
                        (existing_batch["id"],),
                    ).fetchall()
                    affected_tx_ids = [r["transaksi_internal_id"] for r in linked_rows]
                    conn.execute("DELETE FROM mutasi_upload_batch WHERE id = ?", (existing_batch["id"],))

                existing_sigs = {
                    row["dedup_signature"]
                    for row in conn.execute(
                        "SELECT dedup_signature FROM mutasi_bank WHERE rekening_id = ?",
                        (account["id"],),
                    ).fetchall()
                }
                seen_in_batch: set[str] = set()
                rows_to_insert: list[tuple[MutasiRowInput, str]] = []
                for row, sig in zip(payload.rows, signatures, strict=True):
                    if sig in existing_sigs or sig in seen_in_batch:
                        continue
                    seen_in_batch.add(sig)
                    rows_to_insert.append((row, sig))

                batch_id = conn.execute(
                    """
                    INSERT INTO mutasi_upload_batch (
                        rekening_id, uploaded_by_user_id, nama_file, file_hash,
                        metode_ekstraksi, periode_mulai, periode_selesai,
                        saldo_awal_periode, saldo_akhir_periode, jumlah_baris
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        account["id"],
                        user_id,
                        payload.nama_file,
                        payload.file_hash.lower(),
                        payload.metode_ekstraksi,
                        summary.periode_mulai,
                        summary.periode_selesai,
                        summary.saldo_awal_periode,
                        summary.saldo_akhir_periode,
                        len(rows_to_insert),
                    ),
                ).lastrowid

                for row, sig in rows_to_insert:
                    conn.execute(
                        """
                        INSERT INTO mutasi_bank (
                            batch_id, rekening_id, no_rekening, tanggal, waktu,
                            uraian, tipe, nominal, saldo, dedup_signature
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            batch_id,
                            account["id"],
                            no_rek_primary,
                            row.tanggal,
                            row.waktu,
                            row.uraian,
                            row.tipe,
                            row.nominal,
                            row.saldo,
                            sig,
                        ),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        if affected_tx_ids:
            recalculate_reconciliation_for_transactions(affected_tx_ids)
        recon = auto_reconcile_mutasi_batch(batch_id)

        skipped = len(payload.rows) - len(rows_to_insert)
        return {
            "batch_id": batch_id,
            "rekening": account["kode_akun"],
            "inserted_count": len(rows_to_insert),
            "skipped_duplicates": skipped,
            "summary": summary.model_dump(),
            "reconciliation": recon,
            "message": f"Batch mutasi #{batch_id} tersimpan ({len(rows_to_insert)} baris baru, {skipped} duplikat dilewati)",
        }

    def list_batches(self, *, rekening_id: int | None = None, limit: int = 50) -> dict:
        where = ""
        params: list[object] = []
        if rekening_id is not None:
            where = "WHERE b.rekening_id = ?"
            params.append(rekening_id)
        params.append(limit)
        with get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    b.id, b.rekening_id, b.nama_file, b.file_hash, b.metode_ekstraksi,
                    b.periode_mulai, b.periode_selesai, b.saldo_awal_periode,
                    b.saldo_akhir_periode, b.jumlah_baris, b.created_at,
                    rp.kode_akun AS rekening, rp.no_rekening,
                    u.full_name AS uploaded_by
                FROM mutasi_upload_batch b
                JOIN rekening_perusahaan rp ON rp.id = b.rekening_id
                LEFT JOIN users u ON u.id = b.uploaded_by_user_id
                {where}
                ORDER BY b.id DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return {"items": [dict(row) for row in rows]}

    def list_rows(
        self,
        *,
        rekening_id: int | None = None,
        batch_id: int | None = None,
        status_rekonsiliasi: str | None = None,
        tipe: str | None = None,
        tanggal_mulai: str | None = None,
        tanggal_selesai: str | None = None,
        search: str | None = None,
        limit: int = 200,
    ) -> dict:
        clauses: list[str] = []
        params: list[object] = []
        if rekening_id is not None:
            clauses.append("mb.rekening_id = ?")
            params.append(rekening_id)
        if batch_id is not None:
            clauses.append("mb.batch_id = ?")
            params.append(batch_id)
        if status_rekonsiliasi:
            clauses.append("mb.status_rekonsiliasi = ?")
            params.append(status_rekonsiliasi)
        if tipe in {"CR", "DB"}:
            clauses.append("mb.tipe = ?")
            params.append(tipe)
        if tanggal_mulai and tanggal_mulai.strip():
            clauses.append("mb.tanggal >= ?")
            params.append(tanggal_mulai.strip())
        if tanggal_selesai and tanggal_selesai.strip():
            clauses.append("mb.tanggal <= ?")
            params.append(tanggal_selesai.strip())
        if search and search.strip():
            clauses.append("LOWER(mb.uraian) LIKE ?")
            params.append(f"%{search.strip().lower()}%")

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)

        with get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    mb.id, mb.batch_id, mb.rekening_id, mb.no_rekening,
                    mb.tanggal, mb.waktu, mb.uraian, mb.tipe, mb.nominal,
                    mb.saldo, mb.status_rekonsiliasi, mb.penyebab_selisih,
                    rp.kode_akun AS rekening
                FROM mutasi_bank mb
                JOIN rekening_perusahaan rp ON rp.id = mb.rekening_id
                {where}
                ORDER BY mb.tanggal DESC, mb.waktu DESC, mb.id DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return {"items": [dict(row) for row in rows]}

    def delete_batch(self, *, batch_id: int) -> dict:
        with get_connection() as conn:
            batch = conn.execute(
                "SELECT id, nama_file FROM mutasi_upload_batch WHERE id = ?",
                (batch_id,),
            ).fetchone()
            if not batch:
                raise MutasiError("Batch mutasi tidak ditemukan", status_code=404)

            conn.execute("BEGIN IMMEDIATE")
            linked_rows = conn.execute(
                """
                SELECT DISTINCT rm.transaksi_internal_id
                FROM rekonsiliasi_match rm
                JOIN mutasi_bank mb ON mb.id = rm.mutasi_bank_id
                WHERE mb.batch_id = ? AND rm.transaksi_internal_id IS NOT NULL
                """,
                (batch_id,),
            ).fetchall()
            affected_tx_ids = [row["transaksi_internal_id"] for row in linked_rows]
            conn.execute("DELETE FROM mutasi_upload_batch WHERE id = ?", (batch_id,))
            conn.commit()

        recalc = recalculate_reconciliation_for_transactions(affected_tx_ids)
        return {
            "batch_id": batch_id,
            "recalculated_transactions": recalc["recalculated"],
            "rematched_transactions": recalc["rematched"],
            "message": f"Batch #{batch_id} ({batch['nama_file']}) berhasil dihapus",
        }

    def _get_non_cash_account(self, rekening_id: int) -> dict:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT id, kode_akun, bank_lembaga, no_rekening, atas_nama, peran, is_cash
                FROM rekening_perusahaan
                WHERE id = ? AND is_active = 1
                """,
                (rekening_id,),
            ).fetchone()
        if not row:
            raise MutasiError("Rekening tidak ditemukan atau tidak aktif")
        if row["is_cash"]:
            raise MutasiError("Akun Kas Operasional tidak tersedia untuk upload mutasi PDF")
        return dict(row)

    def _find_batch_by_hash(self, file_hash: str) -> dict | None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT b.id, b.nama_file, b.created_at, rp.kode_akun AS rekening
                FROM mutasi_upload_batch b
                JOIN rekening_perusahaan rp ON rp.id = b.rekening_id
                WHERE b.file_hash = ?
                LIMIT 1
                """,
                (file_hash.lower(),),
            ).fetchone()
        return dict(row) if row else None

    def _match_account_by_number(self, detected_no: str | None, accounts: list[dict]) -> dict | None:
        digits = _digits(detected_no)
        if len(digits) < 4:
            return None
        for account in accounts:
            for num in _account_numbers(account["no_rekening"]):
                if digits == num or (len(digits) >= 6 and (digits in num or num in digits)):
                    return account
        return None

    def _compute_batch_signatures(
        self, rekening_id: int, rows: list[MutasiRowInput]
    ) -> list[str]:
        counts: dict[tuple, int] = {}
        signatures: list[str] = []
        for row in rows:
            key = (
                rekening_id,
                row.tanggal,
                row.waktu,
                row.tipe,
                _format_num(row.nominal),
                _normalize_uraian(row.uraian),
            )
            occ = counts.get(key, 0)
            counts[key] = occ + 1
            signatures.append(
                compute_dedup_signature(
                    rekening_id=rekening_id,
                    tanggal=row.tanggal,
                    waktu=row.waktu,
                    tipe=row.tipe,
                    nominal=row.nominal,
                    uraian=row.uraian,
                    saldo=row.saldo,
                    occurrence=occ,
                )
            )
        return signatures

    def _existing_signatures(self, rekening_id: int) -> set[str]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT dedup_signature FROM mutasi_bank WHERE rekening_id = ?",
                (rekening_id,),
            ).fetchall()
        return {row["dedup_signature"] for row in rows}

    def _user_id(self, username: str) -> int:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE username = ?",
                (username.strip().lower(),),
            ).fetchone()
        if not row:
            raise MutasiError("User tidak ditemukan", status_code=401)
        return row["id"]


mutasi_service = MutasiService()
