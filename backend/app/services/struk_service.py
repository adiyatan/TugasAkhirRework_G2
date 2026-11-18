from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import shutil
import uuid

from app.core.config import settings
from app.core.database import get_connection
from app.schemas.auth import UserPublic
from app.schemas.struk import StrukMetadata, StrukSaveRequest
from app.services.storage import (
    UploadValidationError,
    safe_stored_filename,
    storage_root,
    validate_upload,
    write_staging_file,
)
from app.services.vision import VisionImage, complete_vision

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "receipt_extraction.prompt.md"
TAB_TYPES = {"normal", "flip", "slip_gaji", "reimburse"}
TOP_LEVEL_KEYS = {
    "tanggal_transaksi",
    "waktu_transaksi",
    "rekening",
    "rekening_tujuan",
    "tipe",
    "kategori",
    "penerima_pengirim",
    "keterangan",
    "nominal_pokok",
    "biaya_admin_kode_unik",
    "total_mutasi",
    "jenis_struk",
    "slot_a",
    "slot_b",
    "slot_c",
    "notes",
}
FILE_KEYS = {
    "filename",
    "document_type",
    "amount",
    "date",
    "time",
    "sender_digits",
    "recipient_digits",
    "company_account",
    "sender_excluded",
    "is_unpaid",
}
SALARY_CATEGORIES = {"Biaya-Gaji Karyawan", "Pendapatan/Beban Lain"}
PINDAH_BUKU_CATEGORY = "Transfer Antar Rekening (Pindah Buku)"
FLIP_DOC_TYPES = {"flip_bank_to_fliptech", "flip_to_recipient"}


class StrukError(Exception):
    """Base error that the router can translate into an HTTP response."""

    status_code = 400

    def __init__(self, message: str, *, errors: list[str] | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.errors = errors or [message]
        if status_code is not None:
            self.status_code = status_code


class StrukConflictError(StrukError):
    status_code = 409


class StrukUpstreamError(StrukError):
    status_code = 502


@dataclass(frozen=True)
class ReceiptUpload:
    slot: str
    filename: str
    content_type: str
    data: bytes


def _as_int(value: object, default: int = 0) -> int:
    if value is None or isinstance(value, bool):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _digits(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\D", "", str(value))


def _loads_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                payload = json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                raise StrukUpstreamError("Respons vision bukan JSON yang valid") from exc
        else:
            raise StrukUpstreamError("Respons vision bukan JSON yang valid") from exc
    if not isinstance(payload, dict):
        raise StrukUpstreamError("Respons vision harus berupa objek JSON")
    return payload


def _validate_payload(payload: dict, expected_counts: dict[str, int]) -> None:
    missing = TOP_LEVEL_KEYS - set(payload)
    if missing:
        raise StrukUpstreamError(f"Respons vision kehilangan field: {', '.join(sorted(missing))}")

    for key, expected in expected_counts.items():
        rows = payload.get(key)
        if not isinstance(rows, list):
            raise StrukUpstreamError(f"{key} harus berupa array")
        if len(rows) != expected:
            raise StrukUpstreamError(
                f"Jumlah objek {key} ({len(rows)}) tidak sama dengan jumlah file ({expected})"
            )
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise StrukUpstreamError(f"{key}[{index}] harus berupa objek")
            missing_file_keys = FILE_KEYS - set(row)
            if missing_file_keys:
                raise StrukUpstreamError(
                    f"{key}[{index}] kehilangan field: {', '.join(sorted(missing_file_keys))}"
                )


@lru_cache(maxsize=1)
def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def render_prompt(tab_type: str, is_cash: bool, metadata: StrukMetadata) -> str:
    accounts = [row.model_dump() for row in metadata.rekening_perusahaan]
    categories = [row.model_dump() for row in metadata.kategori_sop]
    excluded = [row.model_dump() for row in metadata.rekening_dikecualikan]
    return (
        load_prompt()
        .replace("{{TAB_TYPE}}", tab_type)
        .replace("{{IS_CASH}}", "true" if is_cash else "false")
        .replace("{{REKENING_PERUSAHAAN}}", json.dumps(accounts, ensure_ascii=False, indent=2))
        .replace("{{REKENING_DIKECUALIKAN}}", json.dumps(excluded, ensure_ascii=False, indent=2))
        .replace("{{KATEGORI_SOP}}", json.dumps(categories, ensure_ascii=False, indent=2))
    )


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

    async def extract(
        self,
        *,
        user: UserPublic,
        tab_type: str,
        is_cash: bool,
        slot_a: list[ReceiptUpload],
        slot_b: list[ReceiptUpload],
        slot_c: list[ReceiptUpload],
    ) -> dict:
        if tab_type not in TAB_TYPES:
            raise StrukError("Mode tab tidak valid")
        self._validate_slots(tab_type, is_cash, slot_a, slot_b, slot_c)

        uploads = [*slot_a, *slot_b, *slot_c]
        for upload in uploads:
            try:
                validate_upload(upload.filename, upload.content_type, upload.data)
            except UploadValidationError as exc:
                raise StrukError(str(exc)) from exc
        self._reject_duplicate_hashes(uploads)

        metadata = self.get_metadata()
        images = [
            VisionImage(
                slot=upload.slot,
                filename=upload.filename,
                content_type=upload.content_type,
                data=upload.data,
            )
            for upload in uploads
        ]
        prompt = render_prompt(tab_type, is_cash, metadata)
        try:
            raw = await complete_vision(
                model=settings.vision_model,
                prompt=prompt,
                images=images,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            raise StrukUpstreamError(f"Vision provider gagal: {exc}") from exc

        payload = _loads_json(raw)
        _validate_payload(
            payload,
            {
                "slot_a": len(slot_a),
                "slot_b": len(slot_b),
                "slot_c": len(slot_c),
            },
        )

        extracted, errors, warnings, locked_fields = self._apply_rules(
            tab_type=tab_type,
            is_cash=is_cash,
            payload=payload,
            metadata=metadata,
        )
        manifest = self._build_manifest(uploads, payload)
        staging_id = f"stg_{uuid.uuid4().hex}"
        inserted_files: list[Path] = []
        try:
            for row, upload in zip(manifest, uploads, strict=True):
                stored_name = safe_stored_filename(upload.filename, row["sha256"], upload.slot)
                inserted_files.append(write_staging_file(staging_id, stored_name, upload.data))
                row["stored_name"] = stored_name

            if not errors:
                warning = self._semantic_duplicate_warning(extracted)
                if warning:
                    warnings.append(warning)

            mutasi_hint = self._mutasi_hint(extracted) if not errors else None
            expires_at = (
                datetime.now(timezone.utc) + timedelta(minutes=settings.staging_ttl_minutes)
            ).replace(microsecond=0).isoformat()
            user_id = self._user_id(user.username)
            with get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO upload_staging (
                        id, user_id, tab_type, is_cash, status, manifest_json,
                        extracted_json, expires_at
                    ) VALUES (?, ?, ?, ?, 'OPEN', ?, ?, ?)
                    """,
                    (
                        staging_id,
                        user_id,
                        tab_type,
                        1 if is_cash else 0,
                        json.dumps(manifest, ensure_ascii=False),
                        json.dumps(extracted, ensure_ascii=False),
                        expires_at,
                    ),
                )
                conn.commit()
        except Exception:
            shutil.rmtree(storage_root() / "staging" / staging_id, ignore_errors=True)
            raise

        return {
            "staging_id": staging_id,
            "tab_type": tab_type,
            "is_cash": is_cash,
            "expires_at": expires_at,
            "extracted": extracted,
            "slots": {
                "A": [row for row in manifest if row["slot"] == "A"],
                "B": [row for row in manifest if row["slot"] == "B"],
                "C": [row for row in manifest if row["slot"] == "C"],
            },
            "manifest": manifest,
            "warnings": warnings,
            "errors": errors,
            "locked_fields": locked_fields,
            "mutasi_hint": mutasi_hint,
        }

    def _validate_slots(
        self,
        tab_type: str,
        is_cash: bool,
        slot_a: list[ReceiptUpload],
        slot_b: list[ReceiptUpload],
        slot_c: list[ReceiptUpload],
    ) -> None:
        if not slot_a:
            raise StrukError("Slot A wajib berisi minimal satu file")
        if tab_type == "flip":
            if len(slot_a) != 1:
                raise StrukError("Tab flip wajib memiliki tepat 1 file Slot A")
            if not slot_b:
                raise StrukError("Tab flip wajib memiliki minimal 1 file Slot B")
        elif tab_type in {"slip_gaji", "reimburse"} and not slot_b:
            raise StrukError(f"Tab {tab_type} wajib memiliki minimal 1 file Slot B")
        if is_cash and tab_type != "normal":
            raise StrukError("Transaksi cash hanya tersedia untuk tab normal")

    def _reject_duplicate_hashes(self, uploads: list[ReceiptUpload]) -> None:
        seen: dict[str, str] = {}
        for upload in uploads:
            file_hash = hashlib.sha256(upload.data).hexdigest()
            if file_hash in seen:
                raise StrukError(
                    f"File duplikat di dalam batch: {upload.filename} sama dengan {seen[file_hash]}"
                )
            seen[file_hash] = upload.filename

        for file_hash in seen:
            with get_connection() as conn:
                row = conn.execute(
                    """
                    SELECT fbl.orig_filename, ti.id AS transaksi_id
                    FROM file_bukti_log fbl
                    JOIN transaksi_internal ti ON ti.id = fbl.transaksi_internal_id
                    WHERE fbl.file_hash = ?
                    LIMIT 1
                    """,
                    (file_hash,),
                ).fetchone()
            if row:
                raise StrukConflictError(
                    f"Duplikat file {row['orig_filename']} sudah tercatat pada transaksi #{row['transaksi_id']}"
                )

    def _build_manifest(self, uploads: list[ReceiptUpload], payload: dict) -> list[dict]:
        slot_rows = {
            "A": payload["slot_a"],
            "B": payload["slot_b"],
            "C": payload["slot_c"],
        }
        indexes = {"A": 0, "B": 0, "C": 0}
        manifest: list[dict] = []
        for upload in uploads:
            row = slot_rows[upload.slot][indexes[upload.slot]]
            indexes[upload.slot] += 1
            manifest.append(
                {
                    "slot": upload.slot,
                    "filename": upload.filename,
                    "orig_filename": upload.filename,
                    "content_type": upload.content_type,
                    "size": len(upload.data),
                    "sha256": hashlib.sha256(upload.data).hexdigest(),
                    "document_type": row.get("document_type"),
                    "amount": _as_int(row.get("amount")),
                    "date": row.get("date"),
                    "time": row.get("time"),
                }
            )
        return manifest

    def _apply_rules(
        self,
        *,
        tab_type: str,
        is_cash: bool,
        payload: dict,
        metadata: StrukMetadata,
    ) -> tuple[dict, list[str], list[str], list[str]]:
        errors: list[str] = []
        warnings: list[str] = []
        locked_fields: list[str] = []
        accounts = [row.model_dump() for row in metadata.rekening_perusahaan]
        excluded = [row.model_dump() for row in metadata.rekening_dikecualikan]
        categories = {row.nama_kategori: row for row in metadata.kategori_sop}

        extracted = {
            "tanggal_transaksi": payload.get("tanggal_transaksi"),
            "waktu_transaksi": payload.get("waktu_transaksi") or "12:00:00",
            "rekening": payload.get("rekening"),
            "rekening_tujuan": payload.get("rekening_tujuan"),
            "tipe": payload.get("tipe") or "KELUAR",
            "kategori": payload.get("kategori"),
            "penerima_pengirim": payload.get("penerima_pengirim") or "",
            "keterangan": payload.get("keterangan") or "",
            "nominal_pokok": _as_int(payload.get("nominal_pokok")),
            "biaya_admin_kode_unik": _as_int(payload.get("biaya_admin_kode_unik")),
            "total_mutasi": _as_int(payload.get("total_mutasi")),
            "jenis_struk": payload.get("jenis_struk") or "unknown",
            "notes": payload.get("notes") or "",
            "slot_a": payload["slot_a"],
            "slot_b": payload["slot_b"],
            "slot_c": payload["slot_c"],
        }

        kategori = categories.get(extracted["kategori"])
        if not kategori:
            errors.append("Kategori tidak ada di daftar kategori_sop")
        extracted["kategori_id"] = kategori.id if kategori else None

        if tab_type == "normal":
            slot_a = payload["slot_a"]
            if is_cash:
                cash_account = next((row for row in accounts if row["is_cash"]), None)
                if cash_account:
                    extracted["rekening"] = cash_account["kode_akun"]
                    extracted["rekening_sumber_id"] = cash_account["id"]
                extracted["tipe"] = "KELUAR"
                total = sum(_as_int(row.get("amount")) for row in slot_a)
                extracted["total_mutasi"] = total
                extracted["nominal_pokok"] = total
                extracted["biaya_admin_kode_unik"] = 0
                locked_fields.extend(["rekening", "rekening_sumber_id", "tipe", "total_mutasi"])
            else:
                if any(bool(row.get("is_unpaid")) for row in slot_a):
                    errors.append("Struk Slot A masih berstatus Belum Bayar; gunakan bukti pembayaran yang sah")
                if any(row.get("document_type") in FLIP_DOC_TYPES for row in slot_a):
                    errors.append("Struk Flip terdeteksi di tab normal; gunakan tab flip")
                if any(self._file_is_excluded(row, excluded) for row in slot_a):
                    errors.append(
                        "Pengirim berasal dari rekening_dikecualikan; gunakan tab reimburse"
                    )
                source = self._account_from_file(slot_a[0], accounts, preference="sender")
                destination = self._account_from_file(slot_a[0], accounts, preference="recipient")
                if source:
                    extracted["rekening"] = source["kode_akun"]
                    extracted["rekening_sumber_id"] = source["id"]
                if source and destination and source["id"] != destination["id"]:
                    extracted["tipe"] = "PINDAH_BUKU"
                    extracted["rekening_tujuan"] = destination["kode_akun"]
                    extracted["rekening_tujuan_id"] = destination["id"]
                    extracted["kategori"] = PINDAH_BUKU_CATEGORY
                    extracted["kategori_id"] = categories[PINDAH_BUKU_CATEGORY].id
                    locked_fields.extend(
                        [
                            "tipe",
                            "kategori",
                            "kategori_id",
                            "rekening_tujuan",
                            "rekening_tujuan_id",
                        ]
                    )
                total = sum(_as_int(row.get("amount")) for row in slot_a)
                extracted["total_mutasi"] = total
                extracted["nominal_pokok"] = total
                extracted["biaya_admin_kode_unik"] = 0

        elif tab_type == "flip":
            slot_a = payload["slot_a"][0]
            slot_b = payload["slot_b"]
            source = self._account_from_file(slot_a, accounts, preference="sender")
            if source:
                extracted["rekening"] = source["kode_akun"]
                extracted["rekening_sumber_id"] = source["id"]
            total = _as_int(slot_a.get("amount"))
            nominal = sum(_as_int(row.get("amount")) for row in slot_b)
            biaya = total - nominal
            extracted["total_mutasi"] = total
            extracted["nominal_pokok"] = nominal
            extracted["biaya_admin_kode_unik"] = biaya
            extracted["tanggal_transaksi"] = slot_a.get("date") or extracted["tanggal_transaksi"]
            extracted["waktu_transaksi"] = slot_a.get("time") or extracted["waktu_transaksi"]
            extracted["tipe"] = "KELUAR"
            locked_fields.extend(
                [
                    "tanggal_transaksi",
                    "waktu_transaksi",
                    "rekening",
                    "rekening_sumber_id",
                    "tipe",
                    "nominal_pokok",
                    "biaya_admin_kode_unik",
                    "total_mutasi",
                ]
            )
            if biaya < 0 or biaya > 1000:
                errors.append(
                    "Selisih total mutasi dan nominal pokok Flip di luar batas Rp1.000"
                )
            dates = {row.get("date") for row in slot_b if row.get("date")}
            if dates and extracted["tanggal_transaksi"] not in dates:
                warnings.append("Tanggal Slot A berbeda dengan tanggal Slot B")
            destination = next(
                (
                    account
                    for row in slot_b
                    if (account := self._account_from_file(row, accounts, preference="recipient"))
                ),
                None,
            )
            if destination and source and destination["id"] != source["id"]:
                extracted["tipe"] = "PINDAH_BUKU"
                extracted["rekening_tujuan"] = destination["kode_akun"]
                extracted["rekening_tujuan_id"] = destination["id"]
                extracted["kategori"] = PINDAH_BUKU_CATEGORY
                extracted["kategori_id"] = categories[PINDAH_BUKU_CATEGORY].id
                locked_fields.extend(
                    ["tipe", "kategori", "kategori_id", "rekening_tujuan", "rekening_tujuan_id"]
                )

        elif tab_type == "slip_gaji":
            slot_a = payload["slot_a"]
            slot_b = payload["slot_b"]
            main = next(
                (row for row in slot_b if row.get("document_type") == "flip_bank_to_fliptech"),
                slot_b[0],
            )
            extracted["tanggal_transaksi"] = main.get("date") or extracted["tanggal_transaksi"]
            extracted["waktu_transaksi"] = main.get("time") or extracted["waktu_transaksi"]
            source = self._account_from_file(main, accounts, preference="sender")
            if source:
                extracted["rekening"] = source["kode_akun"]
                extracted["rekening_sumber_id"] = source["id"]
            flip_b = [row for row in slot_b if row.get("document_type") == "flip_to_recipient"]
            total = _as_int(main.get("amount"))
            nominal = sum(_as_int(row.get("amount")) for row in flip_b) if flip_b else total
            biaya = total - nominal
            extracted["tipe"] = "KELUAR"
            extracted["total_mutasi"] = total
            extracted["nominal_pokok"] = nominal
            extracted["biaya_admin_kode_unik"] = biaya
            locked_fields.extend(
                [
                    "tanggal_transaksi",
                    "waktu_transaksi",
                    "rekening",
                    "rekening_sumber_id",
                    "tipe",
                    "total_mutasi",
                    "nominal_pokok",
                ]
            )
            if extracted["kategori"] not in SALARY_CATEGORIES:
                errors.append("Kategori slip gaji harus Biaya-Gaji Karyawan atau Pendapatan/Beban Lain")
            if flip_b and (biaya < 0 or biaya > 1000):
                errors.append("Selisih transfer gaji via Flip di luar batas Rp1.000")
            slip_total = sum(_as_int(row.get("amount")) for row in slot_a)
            if slip_total and slip_total != nominal:
                warnings.append("Nominal slip gaji berbeda dengan nominal transfer")

        elif tab_type == "reimburse":
            slot_a = payload["slot_a"]
            slot_b = payload["slot_b"]
            main = slot_b[0]
            extracted["tanggal_transaksi"] = main.get("date") or extracted["tanggal_transaksi"]
            extracted["waktu_transaksi"] = main.get("time") or extracted["waktu_transaksi"]
            source = self._account_from_file(main, accounts, preference="sender")
            if source:
                extracted["rekening"] = source["kode_akun"]
                extracted["rekening_sumber_id"] = source["id"]
            total = sum(_as_int(row.get("amount")) for row in slot_b)
            nominal = sum(_as_int(row.get("amount")) for row in slot_a)
            extracted["tipe"] = "KELUAR"
            extracted["total_mutasi"] = total
            extracted["nominal_pokok"] = nominal
            extracted["biaya_admin_kode_unik"] = total - nominal
            locked_fields.extend(
                [
                    "tanggal_transaksi",
                    "waktu_transaksi",
                    "rekening",
                    "rekening_sumber_id",
                    "tipe",
                    "total_mutasi",
                    "nominal_pokok",
                ]
            )
            if any(self._file_is_excluded(row, excluded) for row in slot_b):
                errors.append("Pengirim Slot B berasal dari rekening_dikecualikan; reimburse diblokir")
            if abs(total - nominal) > 1000:
                errors.append("Selisih nota awal dan transfer penggantian melebihi Rp1.000")

        if extracted.get("rekening_sumber_id") is None:
            source = next(
                (row for row in accounts if row["kode_akun"] == extracted.get("rekening")),
                None,
            )
            if source:
                extracted["rekening_sumber_id"] = source["id"]
            else:
                errors.append("Rekening sumber tidak dikenal")
        if extracted.get("rekening_tujuan"):
            destination = next(
                (row for row in accounts if row["kode_akun"] == extracted.get("rekening_tujuan")),
                None,
            )
            if destination:
                extracted["rekening_tujuan_id"] = destination["id"]
            else:
                errors.append("Rekening tujuan tidak dikenal")
        else:
            extracted["rekening_tujuan_id"] = None

        return extracted, errors, warnings, sorted(set(locked_fields))

    def _file_is_excluded(self, row: dict, excluded: list[dict]) -> bool:
        if bool(row.get("sender_excluded")):
            return True
        sender = _digits(row.get("sender_digits"))
        if not sender:
            return False
        return any(
            item["potongan_no_rek"] and (
                _digits(item["potongan_no_rek"]) in sender
                or sender in _digits(item["potongan_no_rek"])
            )
            for item in excluded
        )

    def _account_from_file(
        self,
        row: dict,
        accounts: list[dict],
        *,
        preference: str,
    ) -> dict | None:
        company_account = row.get("company_account")
        if company_account:
            match = next((item for item in accounts if item["kode_akun"] == company_account), None)
            if match:
                return match
        digits = _digits(row.get("recipient_digits" if preference == "recipient" else "sender_digits"))
        if not digits:
            return None
        for account in accounts:
            account_digits = _digits(account["no_rekening"])
            if account_digits and (
                digits in account_digits or account_digits in digits
            ):
                return account
        return None

    def _semantic_duplicate_warning(self, extracted: dict) -> str | None:
        if not extracted.get("tanggal_transaksi") or not extracted.get("rekening_sumber_id"):
            return None
        total = extracted.get("total_mutasi") or 0
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT id FROM transaksi_internal
                WHERE tanggal_transaksi = ?
                  AND rekening_sumber_id = ?
                  AND ABS(total_mutasi - ?) <= 1
                ORDER BY id DESC
                LIMIT 1
                """,
                (
                    extracted["tanggal_transaksi"],
                    extracted["rekening_sumber_id"],
                    total,
                ),
            ).fetchone()
        if row:
            return f"Indikasi duplikat transaksi dengan transaksi #{row['id']}"
        return None

    def _mutasi_hint(self, extracted: dict) -> dict | None:
        if not extracted.get("tanggal_transaksi") or not extracted.get("rekening_sumber_id"):
            return None
        try:
            center = date.fromisoformat(extracted["tanggal_transaksi"])
        except ValueError:
            return None
        start = (center - timedelta(days=1)).isoformat()
        end = (center + timedelta(days=1)).isoformat()
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total FROM mutasi_bank
                WHERE rekening_id = ? AND tanggal BETWEEN ? AND ?
                """,
                (extracted["rekening_sumber_id"], start, end),
            ).fetchone()
        if row and row["total"]:
            return {
                "found": True,
                "message": "Ditemukan indikasi kecocokan di mutasi",
            }
        return {"found": False, "message": "Belum ada di mutasi"}

    def save(self, *, user: UserPublic, payload: StrukSaveRequest) -> dict:
        user_id = self._user_id(user.username)
        with get_connection() as conn:
            staging = conn.execute(
                "SELECT * FROM upload_staging WHERE id = ?",
                (payload.staging_id,),
            ).fetchone()
        if not staging:
            raise StrukError("Staging tidak ditemukan", status_code=404)
        if staging["user_id"] != user_id and user.role not in {"finance", "management"}:
            raise StrukError("Staging ini bukan milik user", status_code=403)
        if staging["status"] != "OPEN":
            raise StrukConflictError("Staging sudah diproses atau tidak aktif")
        if self._is_expired(staging["expires_at"]):
            with get_connection() as conn:
                conn.execute(
                    "UPDATE upload_staging SET status = 'EXPIRED' WHERE id = ? AND status = 'OPEN'",
                    (payload.staging_id,),
                )
                conn.commit()
            raise StrukConflictError("Staging sudah kedaluwarsa")

        manifest = json.loads(staging["manifest_json"] or "[]")
        extracted = json.loads(staging["extracted_json"] or "{}")
        tab_type = staging["tab_type"]
        self._validate_locked_fields(tab_type, extracted, payload)
        self._recheck_hashes(manifest)
        self._validate_save_payload(payload, tab_type)
        if not payload.force_save_duplicate:
            duplicate = self._find_semantic_duplicate(payload)
            if duplicate:
                raise StrukConflictError(
                    f"Indikasi duplikat dengan transaksi #{duplicate}; gunakan force_save_duplicate untuk tetap menyimpan"
                )

        moved: list[tuple[Path, Path]] = []
        try:
            moved = self._move_manifest_files(payload.staging_id, manifest)
            with get_connection() as conn:
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    claimed = conn.execute(
                        """
                        UPDATE upload_staging
                        SET status = 'SAVED'
                        WHERE id = ? AND status = 'OPEN'
                        """,
                        (payload.staging_id,),
                    )
                    if claimed.rowcount != 1:
                        raise StrukConflictError("Staging sudah diproses oleh request lain")
                    transaksi_id = conn.execute(
                        """
                        INSERT INTO transaksi_internal (
                            staging_id, created_by_user_id, nama_admin, tanggal_input,
                            sumber_pencatatan, tab_type, tanggal_transaksi, waktu_transaksi,
                            rekening_sumber_id, rekening_tujuan_id, tipe, kategori_id,
                            penerima_pengirim, keterangan, nominal_pokok,
                            biaya_admin_kode_unik, total_mutasi
                        ) VALUES (?, ?, ?, ?, 'INPUT_STRUK', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            payload.staging_id,
                            user_id,
                            user.full_name,
                            date.today().isoformat(),
                            tab_type,
                            payload.tanggal_transaksi,
                            payload.waktu_transaksi,
                            payload.rekening_sumber_id,
                            payload.rekening_tujuan_id,
                            payload.tipe,
                            payload.kategori_id,
                            payload.penerima_pengirim,
                            payload.keterangan,
                            payload.nominal_pokok,
                            payload.biaya_admin_kode_unik,
                            payload.total_mutasi,
                        ),
                    ).lastrowid
                    file_rows = self._insert_file_rows(
                        conn,
                        transaksi_id=transaksi_id,
                        tab_type=tab_type,
                        extracted=extracted,
                        manifest=manifest,
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
        except Exception:
            self._restore_moved_files(moved)
            raise

        shutil.rmtree(storage_root() / "staging" / payload.staging_id, ignore_errors=True)
        return {
            "staging_id": payload.staging_id,
            "transaksi_id": transaksi_id,
            "files": file_rows,
            "message": "Transaksi berhasil disimpan",
        }

    def _is_expired(self, expires_at: str) -> bool:
        try:
            moment = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            return True
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment < datetime.now(timezone.utc)

    def _validate_locked_fields(
        self, tab_type: str, extracted: dict, payload: StrukSaveRequest
    ) -> None:
        locked = self._locked_fields(tab_type, extracted)
        for field in locked:
            expected = extracted.get(field)
            actual = getattr(payload, field)
            if field == "waktu_transaksi" and not expected:
                expected = "12:00:00"
            if actual != expected:
                raise StrukError(f"Field {field} terkunci oleh aturan {tab_type}")

    def _locked_fields(self, tab_type: str, extracted: dict) -> set[str]:
        if tab_type == "flip":
            return {
                "tanggal_transaksi",
                "waktu_transaksi",
                "rekening_sumber_id",
                "tipe",
                "nominal_pokok",
                "biaya_admin_kode_unik",
                "total_mutasi",
            }
        if tab_type in {"slip_gaji", "reimburse"}:
            return {
                "tanggal_transaksi",
                "waktu_transaksi",
                "rekening_sumber_id",
                "tipe",
                "total_mutasi",
                "nominal_pokok",
            }
        if extracted.get("tipe") == "PINDAH_BUKU":
            return {
                "tipe",
                "kategori_id",
                "rekening_tujuan_id",
            }
        if extracted.get("rekening") == "Kas Operasional":
            return {"rekening_sumber_id", "tipe", "total_mutasi"}
        return set()

    def _recheck_hashes(self, manifest: list[dict]) -> None:
        with get_connection() as conn:
            for item in manifest:
                row = conn.execute(
                    """
                    SELECT fbl.orig_filename, ti.id AS transaksi_id
                    FROM file_bukti_log fbl
                    JOIN transaksi_internal ti ON ti.id = fbl.transaksi_internal_id
                    WHERE fbl.file_hash = ?
                    LIMIT 1
                    """,
                    (item["sha256"],),
                ).fetchone()
                if row:
                    raise StrukConflictError(
                        f"Duplikat file {row['orig_filename']} sudah tercatat pada transaksi #{row['transaksi_id']}"
                    )

    def _validate_save_payload(self, payload: StrukSaveRequest, tab_type: str) -> None:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", payload.tanggal_transaksi):
            raise StrukError("Tanggal transaksi tidak valid")
        if not re.fullmatch(r"\d{2}:\d{2}:\d{2}", payload.waktu_transaksi):
            raise StrukError("Waktu transaksi tidak valid")
        if payload.total_mutasi != payload.nominal_pokok + payload.biaya_admin_kode_unik:
            raise StrukError("Total mutasi harus sama dengan nominal pokok ditambah biaya admin/kode unik")
        with get_connection() as conn:
            source = conn.execute(
                "SELECT id FROM rekening_perusahaan WHERE id = ? AND is_active = 1",
                (payload.rekening_sumber_id,),
            ).fetchone()
            category = conn.execute(
                "SELECT id, nama_kategori FROM kategori_sop WHERE id = ? AND is_active = 1",
                (payload.kategori_id,),
            ).fetchone()
        if not source:
            raise StrukError("Rekening sumber tidak valid")
        if not category:
            raise StrukError("Kategori tidak valid")
        if payload.tipe == "PINDAH_BUKU":
            if payload.rekening_tujuan_id is None:
                raise StrukError("Rekening tujuan wajib diisi untuk PINDAH_BUKU")
            if payload.rekening_tujuan_id == payload.rekening_sumber_id:
                raise StrukError("Rekening sumber dan tujuan harus berbeda")
            with get_connection() as conn:
                destination = conn.execute(
                    "SELECT id FROM rekening_perusahaan WHERE id = ? AND is_active = 1",
                    (payload.rekening_tujuan_id,),
                ).fetchone()
            if not destination:
                raise StrukError("Rekening tujuan tidak valid")
        if tab_type == "slip_gaji" and category["nama_kategori"] not in SALARY_CATEGORIES:
            raise StrukError("Kategori slip gaji tidak diizinkan")
        if tab_type == "flip" and payload.tipe not in {"KELUAR", "PINDAH_BUKU"}:
            raise StrukError("Tipe transaksi Flip harus KELUAR atau PINDAH_BUKU")

    def _find_semantic_duplicate(self, payload: StrukSaveRequest) -> int | None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT id FROM transaksi_internal
                WHERE tanggal_transaksi = ?
                  AND rekening_sumber_id = ?
                  AND ABS(total_mutasi - ?) <= 1
                ORDER BY id DESC
                LIMIT 1
                """,
                (
                    payload.tanggal_transaksi,
                    payload.rekening_sumber_id,
                    payload.total_mutasi,
                ),
            ).fetchone()
        return row["id"] if row else None

    def _move_manifest_files(self, staging_id: str, manifest: list[dict]) -> list[tuple[Path, Path]]:
        moved: list[tuple[Path, Path]] = []
        staging_dir = storage_root() / "staging" / staging_id
        files_dir = storage_root() / "files"
        files_dir.mkdir(parents=True, exist_ok=True)
        try:
            for item in manifest:
                source = staging_dir / item["stored_name"]
                destination = files_dir / item["stored_name"]
                if not source.is_file():
                    raise StrukConflictError(f"File staging hilang: {item['orig_filename']}")
                if destination.exists():
                    raise StrukConflictError(f"File permanen sudah ada: {item['stored_name']}")
                source.replace(destination)
                moved.append((source, destination))
        except Exception:
            self._restore_moved_files(moved)
            raise
        return moved

    def _restore_moved_files(self, moved: list[tuple[Path, Path]]) -> None:
        for source, destination in reversed(moved):
            if destination.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                destination.replace(source)

    def _insert_file_rows(
        self,
        conn,
        *,
        transaksi_id: int,
        tab_type: str,
        extracted: dict,
        manifest: list[dict],
    ) -> list[dict]:
        rows: list[dict] = []
        for item in manifest:
            status_file = self._file_status(tab_type, item)
            tanggal_waktu = " ".join(
                part for part in [item.get("date") or "", item.get("time") or ""] if part
            )
            cursor = conn.execute(
                """
                INSERT INTO file_bukti_log (
                    transaksi_internal_id, slot, filename, orig_filename, file_hash,
                    jenis_struk, status_file, nominal_raw, tanggal_waktu_raw,
                    keterangan_raw
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transaksi_id,
                    item["slot"],
                    item["stored_name"],
                    item["orig_filename"],
                    item["sha256"],
                    item.get("document_type") or extracted.get("jenis_struk") or "unknown",
                    status_file,
                    item.get("amount") or 0,
                    tanggal_waktu,
                    extracted.get("notes") or "",
                ),
            )
            rows.append(
                {
                    "id": cursor.lastrowid,
                    "slot": item["slot"],
                    "filename": item["stored_name"],
                    "status_file": status_file,
                }
            )
        return rows

    def _file_status(self, tab_type: str, item: dict) -> str:
        slot = item["slot"]
        if tab_type == "flip":
            if slot == "A":
                return "TERPAKAI_UTAMA"
            if slot == "B":
                return "TERPAKAI_PENDUKUNG_FLIP"
            return "TERPAKAI_NOTA_PENDUKUNG"
        if tab_type == "normal":
            return "TERPAKAI_UTAMA" if slot == "A" else "TERPAKAI_NOTA_PENDUKUNG"
        if tab_type in {"slip_gaji", "reimburse"}:
            return "TERPAKAI_UTAMA" if slot == "B" else "TERPAKAI_NOTA_PENDUKUNG"
        return "TERPAKAI_NOTA_PENDUKUNG"

    def _user_id(self, username: str) -> int:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE username = ?",
                (username.strip().lower(),),
            ).fetchone()
        if not row:
            raise StrukError("User tidak ditemukan", status_code=401)
        return row["id"]


struk_service = StrukService()
